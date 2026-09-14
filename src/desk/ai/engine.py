"""
ODW.ai Desk — AI Engine Orchestrator (AI-005)

Full RAG pipeline: PII detection → model routing → Vault retrieval → LLM inference → confidence scoring.
"""


from dataclasses import dataclass

import structlog
from sqlalchemy import select

from desk.ai.confidence_scorer import ConfidenceScore, ConfidenceScorer
from desk.ai.model_router import ModelTarget, RoutingDecision, get_model_router
from desk.ai.pii_shield import PIIResult, RoutingDirective, get_pii_shield
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
from desk.models.message import Message
from desk.observability.metrics import ESCALATIONS
from desk.observability.tracing import start_span
from desk.persona.integration import get_prompt_builder_with_persona
from desk.policy.engine import PolicyEngine
from desk.schemas.channels import OutboundMessage

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
                    policy_result = await policy_engine.run_pre_generation_hooks(content)

                    if policy_result["policy_decision"] == "block":
                        logger.info("Message blocked by policy", triggers=policy_result["triggers"])
                        return AIResult(
                            text=policy_result["redirect_response"] or t("policy_block_pre", lang),
                            blocked=True,
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

                # Step 3: Vault Retrieval (knowledge base)
                knowledge_docs: list[RetrievedDocument] = []
                try:
                    if not pii_result.pii_detected or pii_result.routing_directive == RoutingDirective.REDACTED_FRONTIER_OK:
                        # Only retrieve knowledge if safe to do so
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
                        conversation_history=conversation_history,
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
                    # Fall back to a canned reply; metadata reflects the intended model.
                    return AIResult(
                        text=t("fallback_reply", lang, snippet=content[:50]),
                        model=routing_decision.model_name,
                        routing=routing_decision.target.value,
                    )

                # Step 5.5: Post-generation Policy Check
                async with AsyncSessionLocal() as db:
                    policy_engine = PolicyEngine(db)
                    post_policy_result = await policy_engine.run_post_generation_hooks(
                        llm_response.text,
                        content,
                    )

                    if post_policy_result["action"] == "block":
                        logger.warning("Response blocked by post-generation policy", violations=post_policy_result["violations"])
                        return AIResult(
                            text=t("policy_block_post", lang),
                            model=llm_response.model,
                            routing=routing_decision.target.value,
                            blocked=True,
                        )

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
