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


class PolicyEngine:
    """
    Policy Engine for response guardrails.

    Implements pre-generation intent detection and post-generation validation
    against the ``response_policies`` table.
    """

    def __init__(self, db: AsyncSession, deployment_id: uuid.UUID | None = None):
        self.db = db
        self.deployment_id = deployment_id

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

        for policy in policies:
            if not self._evaluate_trigger(policy, response_content, conversation_metadata):
                continue

            payload = policy.action_payload or {}
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
        content_lower = content.lower()

        # Keyword matching (also the MVP fallback for classifier/llm_intent
        # triggers — they read the same trigger_config keys).
        if any(keyword.lower() in content_lower for keyword in config.get("keywords", [])):
            return True

        # Regex patterns
        if any(
            re.search(pattern, content, re.IGNORECASE) for pattern in config.get("patterns", [])
        ):
            return True

        # Topic detection (simple keyword lexicon for MVP). Topics may come
        # from trigger_config or the policy-level restricted_topics column.
        topics = set(config.get("topics", [])) | set(policy.restricted_topics or [])
        for topic in topics:
            keywords = TOPIC_KEYWORDS.get(topic.lower())
            if keywords and any(keyword in content_lower for keyword in keywords):
                return True

        # Metadata conditions: all configured pairs must match.
        meta_conditions = config.get("metadata")
        if meta_conditions:
            if metadata is None:
                return False
            return all(metadata.get(key) == value for key, value in meta_conditions.items())

        return False

    async def list_policies(self) -> list[dict[str, Any]]:
        """List all response policies."""
        query = select(ResponsePolicy).order_by(ResponsePolicy.priority.asc())
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
        """Activate or deactivate a policy. Returns None if not found."""
        result = await self.db.execute(select(ResponsePolicy).where(ResponsePolicy.id == policy_id))
        policy = result.scalar_one_or_none()
        if policy is None:
            return None

        policy.is_active = active
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info("Policy updated", policy_id=str(policy.id), is_active=active)
        return policy
