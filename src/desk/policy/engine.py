"""
ODW.ai Desk — Policy Engine (POLICY-003, POLICY-006)

Response policy enforcement with pre-generation and post-generation hooks.

Aligned with the ``response_policies`` schema: ``trigger_type`` /
``trigger_config`` decide WHEN a policy fires, ``action`` /
``action_payload`` decide WHAT happens, and ``applies_to``
("pre" | "post" | "both") decides WHERE in the pipeline it runs.
"""

import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.config import get_settings
from desk.models.response_policy import ResponsePolicy

logger = structlog.get_logger()

VALID_TRIGGER_TYPES = {"keyword", "classifier", "llm_intent"}
VALID_ACTIONS = {
    "template",
    "redirect",
    "inject_context",
    "append_disclaimer",
    "block",
    "escalate",
}
VALID_PHASES = {"pre", "post", "both"}

# Keyword lexicon for topic-based triggers. classifier/llm_intent triggers
# fall back to the same trigger_config keys for the MVP; a real classifier
# integration can slot in behind _evaluate_trigger later.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "competitor": ["competitor", "alternative", "vs", "versus", "better than"],
    "pricing": ["price", "cost", "expensive", "cheap", "discount"],
    "legal": ["legal", "law", "lawyer", "attorney", "sue"],
    "medical": ["medical", "doctor", "health", "diagnosis", "treatment"],
}


def default_deployment_id() -> uuid.UUID:
    """
    Deterministic deployment UUID for single-tenant policy rows.

    Derived from the configured deployment identifier so every process in a
    deployment computes the same value without extra infrastructure.
    """
    settings = get_settings()
    return uuid.uuid5(uuid.NAMESPACE_URL, f"odw-desk:deployment:{settings.deployment_id}")


def _keyword_match(keyword: str, content_lower: str) -> bool:
    """
    Word-boundary keyword match (audit #34).

    Plain substring matching fired 'vs' inside 'TVs' and 'law' inside 'flaw',
    blocking/escalating innocent messages. CJK keywords keep substring
    semantics because Chinese text has no word-delimiting boundaries.
    """
    kw = keyword.lower()
    if not kw:
        return False
    if any("一" <= ch <= "鿿" for ch in kw):
        return kw in content_lower
    return re.search(r"\b" + re.escape(kw) + r"\b", content_lower) is not None


def validate_trigger_config(config: dict[str, Any] | None) -> None:
    """
    Validate trigger_config shape at creation time (audit #32).

    Previously an arbitrary dict was accepted: a non-list keywords value or
    an invalid regex raised on EVERY customer message inside the pipeline,
    taking down all AI replies. Raises ValueError on malformed config.
    """
    if config is None:
        return
    if not isinstance(config, dict):
        raise ValueError("trigger_config must be an object")
    for key in ("keywords", "patterns", "topics"):
        value = config.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"trigger_config.{key} must be a list of strings")
    for pattern in config.get("patterns") or []:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex in trigger_config.patterns: {pattern!r}") from exc
    metadata = config.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("trigger_config.metadata must be an object")


class PolicyEngine:
    """
    Policy Engine for response guardrails.

    Implements pre-generation intent detection and post-generation validation
    against the ``response_policies`` table.
    """

    def __init__(self, db: AsyncSession, deployment_id: uuid.UUID | None = None):
        self.db = db
        # Audit #87: default to the current deployment so evaluation/listing
        # never picks up another deployment's policies on a shared database.
        self.deployment_id = deployment_id if deployment_id is not None else default_deployment_id()

    async def get_active_policies(self, phase: str | None = None) -> list[ResponsePolicy]:
        """
        Get active policies, optionally filtered by pipeline phase.

        Policies with ``applies_to='both'`` are returned for either phase.
        Results are ordered by priority (lower value = higher priority,
        matching the column semantics).
        """
        query = select(ResponsePolicy).where(ResponsePolicy.is_active == True)  # noqa: E712

        if phase:
            query = query.where(ResponsePolicy.applies_to.in_([phase, "both"]))
        if self.deployment_id:
            query = query.where(ResponsePolicy.deployment_id == self.deployment_id)

        query = query.order_by(ResponsePolicy.priority.asc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def run_pre_generation_hooks(
        self,
        message_content: str,
        conversation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run pre-generation policy hooks.

        Checks the inbound customer message against pre-phase policies
        (restricted topics, competitor mentions, ...).

        Returns:
            Dict with policy_decision ("allow" | "redirect" | "escalate" |
            "block"), triggers, and redirect_response (canned reply for
            redirect/block actions, if configured).
        """
        policies = await self.get_active_policies(phase="pre")

        triggers: list[dict[str, Any]] = []
        decision = "allow"
        redirect_response: str | None = None

        for policy in policies:
            if not self._evaluate_trigger(policy, message_content, conversation_metadata):
                continue

            payload = policy.action_payload or {}
            triggers.append(
                {
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "trigger_type": policy.trigger_type,
                    "action": policy.action,
                }
            )

            if policy.action == "block":
                decision = "block"
                redirect_response = payload.get("redirect_message") or payload.get("message")
                break  # Highest-priority terminal action wins; stop scanning.

            if policy.action == "escalate" and decision == "allow":
                decision = "escalate"
            elif policy.action in ("redirect", "template") and decision == "allow":
                decision = "redirect"
                redirect_response = (
                    payload.get("response_template") or payload.get("redirect_message")
                )

        if triggers:
            logger.info(
                "Pre-generation policy triggered",
                triggers=[t["policy_name"] for t in triggers],
                decision=decision,
            )

        return {
            "policy_decision": decision,
            "triggers": triggers,
            "redirect_response": redirect_response,
        }

    async def run_post_generation_hooks(
        self,
        response_content: str,
        original_message: str,
        conversation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run post-generation policy hooks.

        Validates the generated response against post-phase policies.

        Returns:
            Dict with is_valid, violations, and action ("allow" | "block").
            A triggered "block" policy (or severity "error") blocks the reply.
        """
        policies = await self.get_active_policies(phase="post")

        violations: list[dict[str, Any]] = []
        # append_disclaimer actions never block and are not violations; they
        # contribute text the caller appends to the reply. Single evaluation
        # pass (audit #86 — previously evaluated twice and marked is_valid
        # False for disclaimer-only matches).
        append_texts: list[str] = []

        for policy in policies:
            if not self._evaluate_trigger(policy, response_content, conversation_metadata):
                continue

            payload = policy.action_payload or {}
            if policy.action == "append_disclaimer":
                text = payload.get("disclaimer_text") or payload.get("message")
                if text:
                    append_texts.append(str(text))
                continue

            default_severity = "error" if policy.action == "block" else "warning"
            violations.append(
                {
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "trigger_type": policy.trigger_type,
                    "action": policy.action,
                    "severity": payload.get("severity", default_severity),
                }
            )

        if violations:
            logger.warning(
                "Post-generation policy violations",
                violations=[v["policy_name"] for v in violations],
            )

        return {
            "is_valid": len(violations) == 0,
            "violations": violations,
            "append_texts": append_texts,
            "action": (
                "block"
                if any(
                    v["severity"] == "error" or v["action"] == "block" for v in violations
                )
                else "allow"
            ),
        }

    def _evaluate_trigger(
        self,
        policy: ResponsePolicy,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate a policy's trigger against content.

        Args:
            policy: The response policy row
            content: Content to evaluate (customer message or AI reply)
            metadata: Additional conversation metadata

        Returns:
            True if the trigger matches, False otherwise.
        """
        config = policy.trigger_config or {}
        if not isinstance(config, dict):
            logger.warning("Malformed trigger_config skipped", policy_id=str(policy.id))
            return False
        content_lower = content.lower()

        # Defensive shape handling (audit #32): a malformed entry is skipped
        # with a log, never raised — one bad policy must not outage the whole
        # AI pipeline. Shapes are also validated at creation time.
        keywords = config.get("keywords") or []
        if not isinstance(keywords, list):
            keywords = []
        patterns = config.get("patterns") or []
        if not isinstance(patterns, list):
            patterns = []
        topics_cfg = config.get("topics") or []
        if not isinstance(topics_cfg, list):
            topics_cfg = []

        # Keyword matching (also the MVP fallback for classifier/llm_intent
        # triggers — they read the same trigger_config keys). Word-boundary
        # matching per audit #34.
        matched = any(
            _keyword_match(kw, content_lower) for kw in keywords if isinstance(kw, str)
        )

        # Regex patterns — invalid patterns are skipped, not raised.
        if not matched:
            for pattern in patterns:
                if not isinstance(pattern, str):
                    continue
                try:
                    if re.search(pattern, content, re.IGNORECASE):
                        matched = True
                        break
                except re.error:
                    logger.warning(
                        "Invalid policy regex skipped",
                        policy_id=str(policy.id),
                        pattern=pattern,
                    )

        # Topic detection (simple keyword lexicon for MVP). Topics may come
        # from trigger_config or the policy-level restricted_topics column.
        if not matched:
            topics = {t for t in topics_cfg if isinstance(t, str)} | set(
                policy.restricted_topics or []
            )
            for topic in topics:
                topic_keywords = TOPIC_KEYWORDS.get(topic.lower())
                if topic_keywords and any(
                    _keyword_match(kw, content_lower) for kw in topic_keywords
                ):
                    matched = True
                    break

        # Metadata conditions (audit #33): a mandatory AND-gate whenever
        # present — previously a keyword match short-circuited them, so a
        # WhatsApp-only policy fired on every channel.
        meta_conditions = config.get("metadata")
        if not isinstance(meta_conditions, dict):
            meta_conditions = None
        if meta_conditions:
            if metadata is None:
                return False
            if not all(metadata.get(key) == value for key, value in meta_conditions.items()):
                return False

        has_content_trigger = bool(keywords or patterns or topics_cfg or policy.restricted_topics)
        if not has_content_trigger:
            # Metadata-only policy: fires when all metadata conditions match.
            return bool(meta_conditions)

        return matched

    async def list_policies(self) -> list[dict[str, Any]]:
        """List this deployment's response policies (audit #87)."""
        query = select(ResponsePolicy).order_by(ResponsePolicy.priority.asc())
        if self.deployment_id:
            query = query.where(ResponsePolicy.deployment_id == self.deployment_id)
        result = await self.db.execute(query)
        policies = result.scalars().all()

        return [
            {
                "id": str(policy.id),
                "name": policy.name,
                "description": policy.description,
                "trigger_type": policy.trigger_type,
                "trigger_config": policy.trigger_config,
                "action": policy.action,
                "action_payload": policy.action_payload,
                "applies_to": policy.applies_to,
                "priority": policy.priority,
                "restricted_topics": policy.restricted_topics,
                "allow_general_knowledge_fallback": policy.allow_general_knowledge_fallback,
                "is_active": policy.is_active,
                "created_at": policy.created_at.isoformat() if policy.created_at else None,
            }
            for policy in policies
        ]

    async def create_policy(
        self,
        name: str,
        trigger_type: str,
        action: str,
        trigger_config: dict[str, Any] | None = None,
        action_payload: dict[str, Any] | None = None,
        applies_to: str = "pre",
        priority: int = 100,
        description: str | None = None,
        restricted_topics: list[str] | None = None,
        deployment_id: uuid.UUID | None = None,
    ) -> ResponsePolicy:
        """
        Create a new response policy.

        Raises:
            ValueError: If trigger_type, action, or applies_to is invalid.
        """
        if trigger_type not in VALID_TRIGGER_TYPES:
            raise ValueError(
                f"Invalid trigger_type '{trigger_type}'. Valid: {sorted(VALID_TRIGGER_TYPES)}"
            )
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Valid: {sorted(VALID_ACTIONS)}")
        if applies_to not in VALID_PHASES:
            raise ValueError(f"Invalid applies_to '{applies_to}'. Valid: {sorted(VALID_PHASES)}")
        # Audit #32: reject malformed trigger shapes / invalid regexes at
        # creation instead of failing on every customer message at runtime.
        validate_trigger_config(trigger_config)

        policy = ResponsePolicy(
            deployment_id=deployment_id or default_deployment_id(),
            name=name,
            description=description,
            trigger_type=trigger_type,
            trigger_config=trigger_config or {},
            action=action,
            action_payload=action_payload or {},
            applies_to=applies_to,
            priority=priority,
            restricted_topics=restricted_topics,
            is_active=True,
        )
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info("Policy created", policy_id=str(policy.id), name=name, action=action)

        return policy

    async def set_policy_active(self, policy_id: uuid.UUID, active: bool) -> ResponsePolicy | None:
        """Activate or deactivate a policy. Returns None if not found.

        Scoped to this deployment (audit #87) so an admin cannot toggle
        another deployment's policies by id on a shared database.
        """
        query = select(ResponsePolicy).where(ResponsePolicy.id == policy_id)
        if self.deployment_id:
            query = query.where(ResponsePolicy.deployment_id == self.deployment_id)
        result = await self.db.execute(query)
        policy = result.scalar_one_or_none()
        if policy is None:
            return None

        policy.is_active = active
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info("Policy updated", policy_id=str(policy.id), is_active=active)
        return policy
