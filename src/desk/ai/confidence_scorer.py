"""
ODW.ai Desk — Confidence Scorer (AI-007)

Calculates response confidence scores based on model output,
knowledge base relevance, and other factors.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from desk.ai.vault_client import RetrievedDocument

logger = structlog.get_logger()


@dataclass
class ConfidenceScore:
    """Confidence score result."""

    score: float
    should_escalate: bool
    reasoning: str
    factors: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": self.score,
            "should_escalate": self.should_escalate,
            "reasoning": self.reasoning,
            "factors": self.factors,
        }


class ConfidenceScorer:
    """
    Confidence scorer for AI responses.

    Calculates confidence based on:
    - Knowledge base relevance scores
    - Response completeness
    - Model confidence (if available)
    """

    def __init__(
        self,
        escalation_threshold: float = 0.5,
        min_knowledge_score: float = 0.3,
    ):
        """
        Initialize Confidence Scorer.

        Args:
            escalation_threshold: Score below which to escalate
            min_knowledge_score: Minimum knowledge relevance score
        """
        self.escalation_threshold = escalation_threshold
        self.min_knowledge_score = min_knowledge_score

        logger.info(
            "Confidence Scorer initialized",
            escalation_threshold=escalation_threshold,
        )

    async def score(
        self,
        response_text: str,
        knowledge_documents: list[RetrievedDocument] | None = None,
        model_metadata: dict[str, Any] | None = None,
    ) -> ConfidenceScore:
        """
        Calculate confidence score for an AI response.

        Args:
            response_text: Generated response text
            knowledge_documents: Retrieved knowledge documents
            model_metadata: Additional metadata from model

        Returns:
            ConfidenceScore with score and escalation decision
        """
        factors: dict[str, float] = {}

        # Factor 1: Knowledge relevance (0.0 - 1.0)
        knowledge_score = self._score_knowledge(knowledge_documents)
        factors["knowledge_relevance"] = knowledge_score

        # Factor 2: Response completeness (0.0 - 1.0)
        completeness_score = self._score_completeness(response_text)
        factors["response_completeness"] = completeness_score

        # Factor 3: Response length appropriateness (0.0 - 1.0)
        length_score = self._score_length(response_text)
        factors["length_appropriateness"] = length_score

        # Factor 4: Model confidence (if available) (0.0 - 1.0)
        model_score = self._score_model_confidence(model_metadata)
        factors["model_confidence"] = model_score

        # Weighted average
        weights = {
            "knowledge_relevance": 0.4,
            "response_completeness": 0.3,
            "length_appropriateness": 0.1,
            "model_confidence": 0.2,
        }

        total_score = sum(factors[key] * weights[key] for key in weights)

        # Determine escalation
        should_escalate = total_score < self.escalation_threshold

        # Build reasoning
        reasoning_parts = []
        if knowledge_score < self.min_knowledge_score:
            reasoning_parts.append("low knowledge relevance")
        if completeness_score < 0.5:
            reasoning_parts.append("incomplete response")
        if should_escalate:
            reasoning_parts.append(f"below threshold ({total_score:.2f} < {self.escalation_threshold})")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "confidence acceptable"

        logger.info(
            "Confidence score calculated",
            score=total_score,
            should_escalate=should_escalate,
            factors=factors,
        )

        return ConfidenceScore(
            score=total_score,
            should_escalate=should_escalate,
            reasoning=reasoning,
            factors=factors,
        )

    def _score_knowledge(self, documents: list[RetrievedDocument] | None) -> float:
        """Score based on knowledge base relevance."""
        if not documents:
            return 0.3  # Neutral score if no knowledge provided

        if not documents:
            return 0.0

        # Average score of top documents
        avg_score = sum(doc.score for doc in documents) / len(documents)
        return min(avg_score, 1.0)

    def _score_completeness(self, response_text: str) -> float:
        """Score based on response completeness."""
        if not response_text:
            return 0.0

        # Check for completeness indicators
        text_lower = response_text.lower()

        # Positive indicators
        positive_indicators = [
            "here's",
            "here is",
            "you can",
            "please",
            "let me",
            "i can help",
            "the answer is",
            "to resolve",
        ]
        positive_count = sum(1 for ind in positive_indicators if ind in text_lower)

        # Negative indicators (uncertainty)
        negative_indicators = [
            "i don't know",
            "i'm not sure",
            "unfortunately",
            "i cannot",
            "unable to",
        ]
        negative_count = sum(1 for ind in negative_indicators if ind in text_lower)

        # Calculate score
        base_score = 0.5
        base_score += min(positive_count * 0.1, 0.3)
        base_score -= min(negative_count * 0.15, 0.3)

        return max(0.0, min(base_score, 1.0))

    def _score_length(self, response_text: str) -> float:
        """Score based on response length appropriateness."""
        if not response_text:
            return 0.0

        word_count = len(response_text.split())

        # Too short or too long
        if word_count < 10:
            return 0.3
        elif word_count > 200:
            return 0.5
        elif 20 <= word_count <= 100:
            return 1.0
        else:
            return 0.7

    def _score_model_confidence(self, metadata: dict[str, Any] | None) -> float:
        """Extract model confidence from metadata if available."""
        if not metadata:
            return 0.5  # Neutral

        # Some models provide confidence/logprobs
        confidence = metadata.get("confidence")
        if confidence is not None:
            return float(confidence)

        # Default to neutral
        return 0.5
