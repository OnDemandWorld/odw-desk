"""
ODW.ai Desk — AI Engine Orchestrator (AI-005)

Full RAG pipeline: PII detection → model routing → Vault retrieval → LLM inference → confidence scoring.
"""


from dataclasses import dataclass

import structlog
from sqlalchemy import select

from desk.ai.confidence_scorer import ConfidenceScore, ConfidenceScorer
from desk.ai.model_router import ModelTarget, RoutingDecision, get_model_router
from desk.ai.pii_shield import PIIResult, get_pii_shield
from desk.ai.prompt_builder import PromptBuilder
from desk.ai.providers.base import LLMProvider, LLMRequest
from desk.ai.providers.ollama import OllamaProvider
from desk.ai.providers.openai import OpenAIProvider
from desk.ai.vault_client import RetrievedDocument, get_vault_client
from desk.config import get_settings
from desk.conversations.manager import ConversationManager
from desk.conversations.state_machine import ConversationStatus
from desk.db import AsyncSessionLocal
from desk.i18n.service import reply_language, t
from desk.models.ai_configuration import AIConfiguration
from desk.models.message import Message
from desk.observability.metrics import ESCALATIONS
from desk.observability.tracing import start_span
from desk.persona.integration import get_prompt_builder_with_persona
from desk.policy.engine import PolicyEngine
from desk.schemas.channels import OutboundMessage
from desk.utils.encryption import field_encryption_from_settings

logger = structlog.get_logger()


@dataclass
class AIResult:
    """Structured outcome of the AI pipeline for one inbound message."""

    text: str
    """Response text to deliver to the customer."""

    model: str = "unknown"
    """LLM model that produced the response ("stub" on fallback paths)."""

    routing: str = "local"
    """Model-routing target (local / frontier)."""

    confidence: float = 0.0
    """Confidence score assigned to the generated response."""

    escalated: bool = False
    """Whether the conversation was escalated to a human agent."""

    blocked: bool = False
    """Whether a policy hook blocked generation."""


class AIEngine:
    """
    AI Engine orchestrator for the full RAG pipeline.

    Coordinates: PII Shield → Model Router → Vault Client → LLM → Confidence Scorer
    """

    def __init__(self) -> None:
        """Initialize AI Engine with all components."""
        settings = get_settings()

        # Initialize components
        self.pii_shield = get_pii_shield()
        self.model_router = get_model_router()
        self.vault_client = get_vault_client()
        self.prompt_builder = PromptBuilder()
        self.confidence_scorer = ConfidenceScorer(
            escalation_threshold=settings.confidence_threshold,
        )

        # Initialize LLM providers
        self.local_provider: LLMProvider = OllamaProvider(
            endpoint=settings.ollama_endpoint,
            model=settings.local_model_name,
        )

        self.frontier_provider: LLMProvider | None = None
        if settings.frontier_enabled and settings.frontier_api_key:
            if settings.frontier_provider == "openai":
                self.frontier_provider = OpenAIProvider(
                    api_key=settings.frontier_api_key,
                    model=settings.frontier_model_name,
                )

        logger.info("AI Engine initialized with full RAG pipeline")

        # D-4: runtime admin configuration (AIConfiguration row) is re-read
        # with a TTL and applied when its updated_at changes — previously the
        # admin model/threshold settings were persisted but never consumed.
        from desk.admin.runtime_settings import TTLCache

        self._runtime_cfg_cache = TTLCache(ttl_seconds=60)
        self._applied_cfg_stamp: str | None = None

    async def _refresh_runtime_config(self) -> None:
        """Re-read the active AIConfiguration (TTL-cached) and apply changes.

        Best-effort: a DB failure keeps the current providers/threshold.
        """
        # Test doubles build AIEngine without __init__; initialise lazily.
        if not hasattr(self, "_runtime_cfg_cache"):
            from desk.admin.runtime_settings import TTLCache

            self._runtime_cfg_cache = TTLCache(ttl_seconds=60)
            self._applied_cfg_stamp = None

        snapshot = self._runtime_cfg_cache.get()
        if snapshot is None:
            try:
                async with AsyncSessionLocal() as db:
                    cfg = (await db.execute(select(AIConfiguration).limit(1))).scalar_one_or_none()
                    snapshot = {
                        "stamp": cfg.updated_at.isoformat() if cfg and cfg.updated_at else (str(cfg.id) if cfg else ""),
                        "cfg": cfg,
                    }
            except Exception as exc:  # noqa: BLE001
                logger.debug("Runtime config read failed (keeping current)", error=str(exc))
                snapshot = {"stamp": "", "cfg": None}
            self._runtime_cfg_cache.put(snapshot)

        stamp = snapshot["stamp"]
        if stamp == self._applied_cfg_stamp:
            return
        cfg = snapshot["cfg"]
        if cfg is not None:
            # Guard the apply block: a decryption failure (e.g. SECRET_KEY
            # rotated after a frontier key was saved) must not escape into
            # process_detailed and dead-letter EVERY message permanently
            # (audit #13). On failure keep serving with the local provider.
            try:
                settings = get_settings()
                if cfg.local_model_name or cfg.local_model_endpoint:
                    self.local_provider = OllamaProvider(
                        endpoint=cfg.local_model_endpoint or settings.ollama_endpoint,
                        model=cfg.local_model_name or settings.local_model_name,
                    )
                    logger.info(
                        "Applied admin local-model config",
                        model=cfg.local_model_name,
                        endpoint=cfg.local_model_endpoint,
                    )
                if cfg.frontier_provider == "openai" and cfg.frontier_api_key_encrypted:
                    key = field_encryption_from_settings().decrypt(
                        bytes(cfg.frontier_api_key_encrypted).decode("ascii")
                    )
                    self.frontier_provider = OpenAIProvider(
                        api_key=key,
                        model=cfg.frontier_model_name or "gpt-4o-mini",
                    )
                    # Audit #61: keep the router in sync with the effective
                    # admin config — it was frozen from env at first use, so
                    # wizard-configured frontier was never routed to.
                    self.model_router.frontier_enabled = True
                    self.model_router.frontier_model_name = cfg.frontier_model_name or "gpt-4o-mini"
                    self.model_router.frontier_model_endpoint = "https://api.openai.com/v1"
                    logger.info("Applied admin frontier config", model=cfg.frontier_model_name)
                if cfg.confidence_threshold:
                    self.confidence_scorer = ConfidenceScorer(
                        escalation_threshold=cfg.confidence_threshold,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Runtime config apply failed — falling back to local provider",
                    error=str(exc),
                )
                # _select_provider falls back to local when frontier is None.
                self.frontier_provider = None
                self.model_router.frontier_enabled = False
        # Advance the stamp even on failure: retrying the same broken config
        # on every message adds latency and log spam without changing the
        # outcome. A new admin save produces a new stamp and is re-applied.
        self._applied_cfg_stamp = stamp

    async def process(
        self,
        conversation_id: str,
        content: str,
        channel: str,
        recipient: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Process a customer message and return only the response text.

        Backwards-compatible shortcut over :meth:`process_detailed`.
        """
        result = await self.process_detailed(
            conversation_id=conversation_id,
            content=content,
            channel=channel,
            recipient=recipient,
            conversation_history=conversation_history,
        )
        return result.text

    async def process_detailed(
        self,
        conversation_id: str,
        content: str,
        channel: str,
        recipient: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AIResult:
        """
        Process a customer message through the full AI pipeline.

        Args:
            conversation_id: Conversation ID
            content: Customer message content
            channel: Channel type
            recipient: Recipient identifier
            conversation_history: Previous conversation messages

        Returns:
            :class:`AIResult` with the response text plus model, routing and
            confidence metadata, and whether the turn was escalated.
        """
        logger.info("Processing message through AI pipeline", conversation_id=conversation_id)

        # D-4: apply admin-configured model/threshold changes (TTL-cached).
        await self._refresh_runtime_config()

        # V1.6 F-2 (DS3): wrap the whole pipeline in a best-effort span so the
        # request's span tree captures end-to-end AI processing time. The span
        # never changes the response; sampling/export default to console/1.0.
        with start_span(
            "ai.process",
            {"conversation_id": conversation_id, "channel": channel},
        ) as span:
            # Detect the reply language from the inbound message (F-Desk-1). Defaults
            # to English so detection failures keep the existing behaviour.
            lang = reply_language(content)

            try:
                # Step 1: PII Detection
                pii_result: PIIResult = await self.pii_shield.analyze(content)
                logger.info(
                    "PII detection complete",
                    pii_detected=pii_result.pii_detected,
                    routing_directive=pii_result.routing_directive.value,
                )

                # Write the findings back to the stored customer message so the
                # inbox surfaces PII flags/redacted text — previously analysis
                # results only fed routing and never reached the message row
                # (R1 acceptance finding, 2026-09-12). Best-effort: never break
                # the AI path on a bookkeeping failure.
                try:
                    async with AsyncSessionLocal() as pii_db:
                        msg_result = await pii_db.execute(
                            select(Message)
                            .where(
                                Message.conversation_id == conversation_id,
                                Message.sender_type == "customer",
                            )
                            .order_by(Message.created_at.desc(), Message.id.desc())
                            .limit(1)
                        )
                        customer_message = msg_result.scalar_one_or_none()
                        if customer_message is not None:
                            customer_message.pii_detected = pii_result.pii_detected
                            customer_message.pii_types = pii_result.pii_types
                            customer_message.content_redacted = (
                                pii_result.redacted_text if pii_result.pii_detected else None
                            )
                            await pii_db.commit()
                except Exception as write_back_err:  # noqa: BLE001
                    logger.warning(
                        "PII write-back failed (best-effort)",
                        conversation_id=conversation_id,
                        error=f"{type(write_back_err).__name__}: {write_back_err}",
                    )

                # Step 1.5: Pre-generation Policy Check
                async with AsyncSessionLocal() as db:
                    policy_engine = PolicyEngine(db)
                    # Audit #33: pass conversation metadata so channel-scoped
                    # policies can fire (previously always None — inert).
                    policy_result = await policy_engine.run_pre_generation_hooks(
                        content, conversation_metadata={"channel": channel}
                    )

                    if policy_result["policy_decision"] == "block":
                        logger.info("Message blocked by policy", triggers=policy_result["triggers"])
                        return AIResult(
                            text=policy_result["redirect_response"] or t("policy_block_pre", lang),
                            blocked=True,
                        )

                    if policy_result["policy_decision"] == "redirect":
                        # Configured redirect (e.g. competitor mentions → canned
                        # reply). Previously the decision was silently dropped
                        # and the LLM answered freely — the guard did not guard.
                        logger.info(
                            "Message redirected by policy",
                            triggers=policy_result["triggers"],
                        )
                        return AIResult(
                            text=policy_result["redirect_response"] or t("policy_block_pre", lang),
                            blocked=True,
                        )

                    if policy_result["policy_decision"] == "escalate":
                        # FR-RP-08: policy-mandated human handoff. Reuse the
                        # low-confidence escalation machinery with a synthetic
                        # score so the conversation lands in the agent inbox.
                        logger.info(
                            "Escalating to human by policy",
                            triggers=policy_result["triggers"],
                        )
                        await self._escalate_conversation(
                            conversation_id,
                            ConfidenceScore(
                                score=0.0,
                                should_escalate=True,
                                reasoning=f"policy: {policy_result['triggers']}",
                                factors={},
                            ),
                        )
                        return AIResult(
                            text=t("escalation_notice", lang),
                            escalated=True,
                        )

                # Step 2: Model Routing
                routing_decision: RoutingDecision = await self.model_router.route(
                    pii_directive=pii_result.routing_directive,
                    text=content,
                    context_depth=len(conversation_history) if conversation_history else 0,
                )
                logger.info(
                    "Model routing complete",
                    target=routing_decision.target.value,
                    model=routing_decision.model_name,
                )

                # Audit #4: history must obey the same PII gate as the current
                # message. Raw prior customer turns were previously sent
                # verbatim to frontier models even when the shield redacted
                # the current turn — defeating the sovereignty guarantee.
                history_for_prompt = conversation_history
                if routing_decision.target == ModelTarget.FRONTIER and conversation_history:
                    history_for_prompt = []
                    for entry in conversation_history:
                        if entry.get("role") == "customer" and entry.get("content"):
                            hist_pii = await self.pii_shield.analyze(entry["content"])
                            history_for_prompt.append(
                                {**entry, "content": hist_pii.redacted_text}
                            )
                        else:
                            history_for_prompt.append(entry)

                # Step 3: Vault Retrieval (knowledge base)
                knowledge_docs: list[RetrievedDocument] = []
                try:
                    # Audit #53: Vault is operator-local, so retrieval is safe
                    # even for LOCAL_MODEL_ONLY turns (query is redacted when
                    # PII was detected). Skipping it capped every PII-bearing
                    # message at confidence 0.56 — below the escalation
                    # threshold — so the AI could never answer them.
                    knowledge_docs = await self.vault_client.retrieve(
                        query=pii_result.redacted_text if pii_result.pii_detected else content,
                        top_k=5,
                    )
                    logger.info("Knowledge retrieval complete", documents=len(knowledge_docs))
                except Exception as e:
                    logger.warning("Knowledge retrieval failed (continuing without)", error=str(e))
                    # Continue without knowledge

                # Step 4: Build Prompt with Persona
                async with AsyncSessionLocal() as db:
                    persona_prompt_builder = await get_prompt_builder_with_persona(db)
                    system_prompt, prompt = await persona_prompt_builder.build_prompt_with_persona(
                        user_message=pii_result.redacted_text if pii_result.pii_detected else content,
                        conversation_history=history_for_prompt,
                        knowledge_context=[doc.to_dict() for doc in knowledge_docs],
                    )

                # Step 5: LLM Inference
                llm_request = LLMRequest(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=1024,
                    temperature=0.7,
                )

                # Select provider based on routing decision
                provider = self._select_provider(routing_decision)
                try:
                    llm_response = await provider.generate(llm_request)
                    logger.info(
                        "LLM inference complete",
                        provider=llm_response.provider,
                        model=llm_response.model,
                        tokens=llm_response.tokens_used,
                    )
                except Exception as e:
                    logger.error("LLM inference failed", error=str(e))
                    # Audit #59: execute the fallback chain instead of acking a
                    # canned non-answer as success — try the local provider,
                    # then escalate to a human if everything fails.
                    fallback_response = None
                    if provider is not self.local_provider:
                        try:
                            fallback_response = await self.local_provider.generate(llm_request)
                            logger.info(
                                "Local fallback inference complete",
                                model=fallback_response.model,
                            )
                        except Exception as fallback_err:  # noqa: BLE001
                            logger.error("Local fallback failed", error=str(fallback_err))
                    if fallback_response is None:
                        await self._escalate_conversation(
                            conversation_id,
                            ConfidenceScore(
                                score=0.0,
                                should_escalate=True,
                                reasoning="provider_failure",
                                factors={},
                            ),
                        )
                        return AIResult(
                            text=t("escalation_notice", lang),
                            model=routing_decision.model_name,
                            routing=routing_decision.target.value,
                            escalated=True,
                        )
                    llm_response = fallback_response

                # Step 5.5: Post-generation Policy Check
                async with AsyncSessionLocal() as db:
                    policy_engine = PolicyEngine(db)
                    post_policy_result = await policy_engine.run_post_generation_hooks(
                        llm_response.text,
                        content,
                        conversation_metadata={"channel": channel},
                    )

                    if post_policy_result["action"] == "block":
                        logger.warning("Response blocked by post-generation policy", violations=post_policy_result["violations"])
                        return AIResult(
                            text=t("policy_block_post", lang),
                            model=llm_response.model,
                            routing=routing_decision.target.value,
                            blocked=True,
                        )

                    # append_disclaimer policies: attach the configured
                    # disclaimer text to the generated reply instead of
                    # dropping it (previously the action was a no-op).
                    disclaimers = [
                        str(d)
                        for d in post_policy_result.get("append_texts", [])
                        if d
                    ]
                    if disclaimers:
                        llm_response.text = llm_response.text + "\n\n" + "\n\n".join(disclaimers)

                # Step 6: Confidence Scoring
                confidence: ConfidenceScore = await self.confidence_scorer.score(
                    response_text=llm_response.text,
                    knowledge_documents=knowledge_docs,
                    model_metadata=llm_response.metadata,
                )

                logger.info(
                    "Confidence scoring complete",
                    score=confidence.score,
                    should_escalate=confidence.should_escalate,
                )

                # Step 7: Decision
                if confidence.should_escalate:
                    # Escalate to human agent
                    logger.warning(
                        "Low confidence, escalating to human",
                        score=confidence.score,
                        reasoning=confidence.reasoning,
                    )
                    # Flip the conversation to ESCALATED and notify agents so
                    # the escalation is actionable, not just a notice text.
                    await self._escalate_conversation(conversation_id, confidence)
                    return AIResult(
                        text=t("escalation_notice", lang),
                        model=llm_response.model,
                        routing=routing_decision.target.value,
                        confidence=confidence.score,
                        escalated=True,
                    )

                # Return AI response
                return AIResult(
                    text=llm_response.text,
                    model=llm_response.model,
                    routing=routing_decision.target.value,
                    confidence=confidence.score,
                )

            except Exception as e:
                span.set_attribute("error", str(e))
                logger.error("AI pipeline failed", error=str(e), conversation_id=conversation_id)
                # Return a safe fallback (stub response for testing)
                return AIResult(text=t("fallback_reply", lang, snippet=content[:50]))

    async def _escalate_conversation(
        self,
        conversation_id: str,
        confidence: ConfidenceScore,
    ) -> None:
        """
        Move the conversation to ESCALATED and notify connected agents.

        Best-effort: a failure here must never block the escalation notice
        from reaching the customer, so every step is guarded.
        """
        ESCALATIONS.labels(reason="low_confidence").inc()
        try:
            # Local import keeps the agents realtime layer out of the AI
            # module's import graph at load time.
            from desk.agents.websocket import broadcast_escalation

            async with AsyncSessionLocal() as db:
                manager = ConversationManager(db)
                conversation = await manager.get_conversation_by_id(conversation_id)
                if (
                    conversation is not None
                    and conversation.status != ConversationStatus.ESCALATED
                ):
                    await manager.update_status(
                        conversation,
                        ConversationStatus.ESCALATED,
                        reason=f"AI confidence {confidence.score:.2f} below threshold",
                    )
                    await db.commit()

            await broadcast_escalation(
                str(conversation_id),
                {
                    "reason": "low_confidence",
                    "confidence": confidence.score,
                    "reasoning": confidence.reasoning,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Escalation side effects failed (best-effort)",
                conversation_id=str(conversation_id),
                error=str(exc),
            )

    def _select_provider(self, routing_decision: RoutingDecision) -> LLMProvider:
        """Select LLM provider based on routing decision."""
        if routing_decision.target == ModelTarget.FRONTIER and self.frontier_provider:
            return self.frontier_provider
        else:
            return self.local_provider

    async def create_outbound_message(
        self,
        conversation_id: str,
        channel: str,
        recipient: str,
        content: str,
    ) -> OutboundMessage:
        """
        Create an OutboundMessage from generated content.

        Args:
            conversation_id: Conversation ID
            channel: Channel type
            recipient: Recipient identifier
            content: Response content

        Returns:
            OutboundMessage
        """
        from typing import Literal, cast

        ChannelType = Literal["whatsapp", "webchat", "email", "telegram", "discord", "slack", "signal"]
        return OutboundMessage(
            conversation_id=conversation_id,
            channel=cast(ChannelType, channel),
            recipient_identifier=recipient,
            content=content,
        )


# Global instance for convenience
_ai_engine: AIEngine | None = None


def get_ai_engine() -> AIEngine:
    """Get or create global AI Engine instance."""
    global _ai_engine
    if _ai_engine is None:
        _ai_engine = AIEngine()
    return _ai_engine
