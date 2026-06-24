"""
ODW.ai Desk — Model Router (AI-002)

Selects inference target (local vs. frontier) based on routing policy,
PII detection result, and complexity scoring. Implements fallback logic.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

from desk.ai.pii_shield import RoutingDirective

logger = structlog.get_logger()


class ModelTarget(StrEnum):
    """Model target types."""

    LOCAL = "local"
    FRONTIER = "frontier"
    ESCALATE = "escalate"


@dataclass
class RoutingDecision:
    """Result of model routing decision."""

    target: ModelTarget
    model_endpoint: str
    model_name: str
    fallback_chain: list[str]
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target": self.target.value,
            "model_endpoint": self.model_endpoint,
            "model_name": self.model_name,
            "fallback_chain": self.fallback_chain,
            "reasoning": self.reasoning,
        }


class ComplexityScorer:
    """
    Heuristic complexity scorer for messages.

    Scores based on message length, question type, context depth, etc.
    """

    @staticmethod
    async def score(text: str, context_depth: int = 0) -> float:
        """
        Calculate complexity score for a message.

        Args:
            text: Message text
            context_depth: Number of messages in conversation context

        Returns:
            Complexity score (0.0 to 1.0)
        """
        if not text:
            return 0.0

        score = 0.0

        # Length factor (longer messages are more complex)
        word_count = len(text.split())
        if word_count > 50:
            score += 0.3
        elif word_count > 20:
            score += 0.15

        # Question indicators
        question_words = ["how", "what", "why", "when", "where", "who", "which", "can", "could", "would", "should"]
        text_lower = text.lower()
        if any(word in text_lower for word in question_words):
            score += 0.2
        if "?" in text:
            score += 0.1

        # Context depth (more context = more complex)
        if context_depth > 5:
            score += 0.2
        elif context_depth > 2:
            score += 0.1

        # Technical terms (simple heuristic)
        technical_indicators = ["error", "bug", "issue", "problem", "fix", "install", "configure", "api", "database"]
        if any(indicator in text_lower for indicator in technical_indicators):
            score += 0.15

        # Normalize to 0.0-1.0
        return min(score, 1.0)


class ModelRouter:
    """
    Model Router for selecting inference targets.

    Routes to local or frontier models based on PII directive,
    complexity score, and configuration.
    """

    def __init__(
        self,
        local_model_endpoint: str,
        local_model_name: str,
        frontier_model_endpoint: str | None,
        frontier_model_name: str | None,
        frontier_enabled: bool = False,
        complexity_threshold: float = 0.6,
    ):
        """
        Initialize Model Router.

        Args:
            local_model_endpoint: Local model endpoint URL
            local_model_name: Local model name
            frontier_model_endpoint: Frontier model endpoint URL
            frontier_model_name: Frontier model name
            frontier_enabled: Whether frontier models are enabled
            complexity_threshold: Complexity threshold for frontier routing
        """
        self.local_model_endpoint = local_model_endpoint
        self.local_model_name = local_model_name
        self.frontier_model_endpoint = frontier_model_endpoint
        self.frontier_model_name = frontier_model_name
        self.frontier_enabled = frontier_enabled
        self.complexity_threshold = complexity_threshold

        self.complexity_scorer = ComplexityScorer()

        logger.info(
            "Model Router initialized",
            local_model=local_model_name,
            frontier_enabled=frontier_enabled,
            complexity_threshold=complexity_threshold,
        )

    async def route(
        self,
        pii_directive: RoutingDirective,
        text: str,
        context_depth: int = 0,
    ) -> RoutingDecision:
        """
        Route to appropriate model based on PII directive and complexity.

        Args:
            pii_directive: Routing directive from PII Shield
            text: Message text (for complexity scoring)
            context_depth: Conversation context depth

        Returns:
            RoutingDecision with target model and fallback chain
        """
        # Calculate complexity score
        complexity_score = await self.complexity_scorer.score(text, context_depth)

        # Apply routing logic
        if pii_directive == RoutingDirective.LOCAL_MODEL_ONLY:
            # PII detected, must use local model
            return RoutingDecision(
                target=ModelTarget.LOCAL,
                model_endpoint=self.local_model_endpoint,
                model_name=self.local_model_name,
                fallback_chain=["escalate_to_human"],
                reasoning=f"PII detected, forcing local model (complexity: {complexity_score:.2f})",
            )

        elif pii_directive == RoutingDirective.REDACTED_FRONTIER_OK:
            # PII detected but redacted, frontier allowed
            if self.frontier_enabled and self.frontier_model_endpoint:
                return RoutingDecision(
                    target=ModelTarget.FRONTIER,
                    model_endpoint=self.frontier_model_endpoint,
                    model_name=self.frontier_model_name or "frontier",
                    fallback_chain=[self.local_model_name, "escalate_to_human"],
                    reasoning=f"PII redacted, using frontier model (complexity: {complexity_score:.2f})",
                )
            else:
                return RoutingDecision(
                    target=ModelTarget.LOCAL,
                    model_endpoint=self.local_model_endpoint,
                    model_name=self.local_model_name,
                    fallback_chain=["escalate_to_human"],
                    reasoning=f"Frontier disabled, falling back to local (complexity: {complexity_score:.2f})",
                )

        else:  # NO_RESTRICTION
            # No PII, route based on complexity
            if complexity_score >= self.complexity_threshold:
                # Complex query, prefer frontier if available
                if self.frontier_enabled and self.frontier_model_endpoint:
                    return RoutingDecision(
                        target=ModelTarget.FRONTIER,
                        model_endpoint=self.frontier_model_endpoint,
                        model_name=self.frontier_model_name or "frontier",
                        fallback_chain=[self.local_model_name, "escalate_to_human"],
                        reasoning=f"High complexity ({complexity_score:.2f}), using frontier model",
                    )
                else:
                    return RoutingDecision(
                        target=ModelTarget.LOCAL,
                        model_endpoint=self.local_model_endpoint,
                        model_name=self.local_model_name,
                        fallback_chain=["escalate_to_human"],
                        reasoning=f"High complexity ({complexity_score:.2f}), but frontier disabled",
                    )
            else:
                # Simple query, use local model
                return RoutingDecision(
                    target=ModelTarget.LOCAL,
                    model_endpoint=self.local_model_endpoint,
                    model_name=self.local_model_name,
                    fallback_chain=[self.frontier_model_name, "escalate_to_human"] if self.frontier_enabled else ["escalate_to_human"],
                    reasoning=f"Low complexity ({complexity_score:.2f}), using local model",
                )


# Global instance
_model_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Get or create global Model Router instance."""
    global _model_router
    if _model_router is None:
        from desk.config import get_settings

        settings = get_settings()
        _model_router = ModelRouter(
            local_model_endpoint=settings.ollama_endpoint,
            local_model_name=settings.local_model_name,
            frontier_model_endpoint="https://api.openai.com/v1" if settings.frontier_provider == "openai" else None,
            frontier_model_name=settings.frontier_model_name if settings.frontier_enabled else None,
            frontier_enabled=settings.frontier_enabled,
            complexity_threshold=0.6,  # TODO: Make configurable
        )
    return _model_router
