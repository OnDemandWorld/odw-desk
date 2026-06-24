"""
ODW.ai Desk — Policy Engine (POLICY-003, POLICY-006)

Response policy enforcement with pre-generation and post-generation hooks.
"""

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.models.response_policy import ResponsePolicy

logger = structlog.get_logger()


class PolicyEngine:
    """
    Policy Engine for response guardrails.

    Implements pre-generation intent detection and post-generation validation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_policies(self, hook_type: str | None = None) -> list[ResponsePolicy]:
        """Get all active policies, optionally filtered by hook type."""
        query = select(ResponsePolicy).where(ResponsePolicy.is_active == True)  # noqa: E712

        if hook_type:
            query = query.where(ResponsePolicy.hook_type == hook_type)

        query = query.order_by(ResponsePolicy.priority.desc())
        result = await self.db.execute(query)
        return result.scalars().all()

    async def run_pre_generation_hooks(
        self,
        message_content: str,
        conversation_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run pre-generation policy hooks.

        Checks for restricted topics, competitor mentions, etc.
        Returns routing directive and any policy triggers.

        Args:
            message_content: Customer message content
            conversation_metadata: Conversation metadata

        Returns:
            Dict with policy_decision, triggers, and action
        """
        policies = await self.get_active_policies(hook_type="pre_generation")

        triggers = []
        action = "allow"  # Default: allow generation
        redirect_response = None

        for policy in policies:
            # Check conditions
            if self._evaluate_conditions(policy.conditions or {}, message_content, conversation_metadata):
                triggers.append({
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "rule_type": policy.rule_type,
                })

                # Determine action based on policy
                if policy.action_type == "block":
                    action = "block"
                    redirect_response = policy.action_config.get("redirect_message") if policy.action_config else None
                    break
                elif policy.action_type == "redirect" and action != "block":
                    action = "redirect"
                    redirect_response = policy.action_config.get("redirect_message") if policy.action_config else None
                elif policy.action_type == "flag":
                    action = "flag"

        # Log policy decision
        if triggers:
            logger.info(
                "Pre-generation policy triggered",
                triggers=[t["policy_name"] for t in triggers],
                action=action,
            )

        return {
            "policy_decision": action,
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

        Validates generated response against policies.

        Args:
            response_content: Generated AI response
            original_message: Original customer message
            conversation_metadata: Conversation metadata

        Returns:
            Dict with validation result and any violations
        """
        policies = await self.get_active_policies(hook_type="post_generation")

        violations = []

        for policy in policies:
            # Check conditions
            if self._evaluate_conditions(policy.conditions or {}, response_content, conversation_metadata):
                violations.append({
                    "policy_id": str(policy.id),
                    "policy_name": policy.name,
                    "rule_type": policy.rule_type,
                    "severity": policy.action_config.get("severity", "warning") if policy.action_config else "warning",
                })

        # Determine overall validation result
        is_valid = len(violations) == 0

        # Log validation result
        if violations:
            logger.warning(
                "Post-generation policy violations",
                violations=[v["policy_name"] for v in violations],
            )

        return {
            "is_valid": is_valid,
            "violations": violations,
            "action": "block" if any(v.get("severity") == "error" for v in violations) else "allow",
        }

    def _evaluate_conditions(
        self,
        conditions: dict[str, Any],
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Evaluate policy conditions against content.

        Args:
            conditions: Policy conditions dict
            content: Content to evaluate
            metadata: Additional metadata

        Returns:
            True if conditions match, False otherwise
        """
        content_lower = content.lower()

        # Keyword matching
        if "keywords" in conditions:
            keywords = conditions["keywords"]
            if any(keyword.lower() in content_lower for keyword in keywords):
                return True

        # Regex patterns
        if "patterns" in conditions:
            import re
            patterns = conditions["patterns"]
            if any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns):
                return True

        # Topic detection (simple keyword-based for MVP)
        if "topics" in conditions:
            topics = conditions["topics"]
            topic_keywords = {
                "competitor": ["competitor", "alternative", "vs", "versus", "better than"],
                "pricing": ["price", "cost", "expensive", "cheap", "discount"],
                "legal": ["legal", "law", "lawyer", "attorney", "sue"],
                "medical": ["medical", "doctor", "health", "diagnosis", "treatment"],
            }
            for topic in topics:
                if topic in topic_keywords:
                    if any(kw in content_lower for kw in topic_keywords[topic]):
                        return True

        # Metadata conditions
        if metadata and "metadata" in conditions:
            meta_conditions = conditions["metadata"]
            for key, value in meta_conditions.items():
                if metadata.get(key) != value:
                    return False

        return False

    async def list_policies(self) -> list[dict[str, Any]]:
        """List all response policies."""
        query = select(ResponsePolicy).order_by(ResponsePolicy.priority.desc())
        result = await self.db.execute(query)
        policies = result.scalars().all()

        return [
            {
                "id": str(policy.id),
                "name": policy.name,
                "description": policy.description,
                "hook_type": policy.hook_type,
                "rule_type": policy.rule_type,
                "action_type": policy.action_type,
                "priority": policy.priority,
                "is_active": policy.is_active,
                "conditions": policy.conditions,
                "created_at": policy.created_at.isoformat() if policy.created_at else None,
            }
            for policy in policies
        ]

    async def create_policy(
        self,
        name: str,
        hook_type: str,
        rule_type: str,
        action_type: str,
        conditions: dict[str, Any],
        action_config: dict[str, Any] | None = None,
        priority: int = 0,
        description: str | None = None,
    ) -> ResponsePolicy:
        """Create a new response policy."""
        policy = ResponsePolicy(
            name=name,
            description=description,
            hook_type=hook_type,
            rule_type=rule_type,
            action_type=action_type,
            conditions=conditions,
            action_config=action_config or {},
            priority=priority,
            is_active=True,
        )
        self.db.add(policy)
        await self.db.commit()
        await self.db.refresh(policy)

        logger.info("Policy created", policy_id=str(policy.id), name=name)

        return policy
