"""
ODW.ai Desk — PII Shield (AI-001)

Detects personally identifiable information (PII) in messages,
generates redacted versions, and issues routing directives.
"""

import re
from enum import StrEnum
from typing import Any

import structlog
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_anonymizer import AnonymizerEngine

logger = structlog.get_logger()

# Presidio ships English-focused recognizers only; with language="en" Chinese
# PII (11-digit mobile numbers, resident IDs) passed through undetected — a
# critical gap for a suite whose primary users write Chinese (R1 acceptance,
# 2026-09-12). These regex recognizers merge into the Presidio result set.
_CN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PHONE_NUMBER", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("PHONE_NUMBER", re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")),
    (
        "ID_CARD",
        re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])\d{3}[\dXx](?!\d)"),
    ),
)


def _cn_recognizer_results(text: str) -> list:
    """Regex-based recogniser results for Chinese PII, deduped against overlap."""
    found: list[RecognizerResult] = []
    for entity_type, pattern in _CN_PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.span()
            if any(r.start <= start and end <= r.end for r in found):
                continue
            found.append(RecognizerResult(entity_type=entity_type, start=start, end=end, score=1.0))
    return found


class RoutingDirective(StrEnum):
    """Routing directives based on PII detection."""

    LOCAL_MODEL_ONLY = "local_model_only"
    REDACTED_FRONTIER_OK = "redacted_frontier_ok"
    NO_RESTRICTION = "no_restriction"


class PIIResult:
    """Result of PII detection and redaction."""

    def __init__(
        self,
        original_text: str,
        pii_detected: bool,
        pii_types: list[str],
        redacted_text: str,
        routing_directive: RoutingDirective,
        pii_entities: list[dict[str, Any]] | None = None,
    ):
        self.original_text = original_text
        self.pii_detected = pii_detected
        self.pii_types = pii_types
        self.redacted_text = redacted_text
        self.routing_directive = routing_directive
        self.pii_entities = pii_entities or []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pii_detected": self.pii_detected,
            "pii_types": self.pii_types,
            "routing_directive": self.routing_directive.value,
            "redacted_text": self.redacted_text,
            "pii_count": len(self.pii_entities),
        }


class PIIShield:
    """
    PII Shield for detecting and redacting personally identifiable information.

    Uses Presidio for NER-based detection and anonymization.
    Issues routing directives based on PII presence and configuration.
    """

    # PII entity types to detect (Presidio entity names)
    DEFAULT_ENTITY_TYPES = [
        "PERSON",  # Names
        "PHONE_NUMBER",
        "EMAIL_ADDRESS",
        "LOCATION",  # Physical addresses
        "DATE_TIME",  # Dates of birth
        "CREDIT_CARD",
        "CRYPTO",
        "IBAN_CODE",
        "IP_ADDRESS",
        "US_SSN",
        "US_PASSPORT",
        "US_DRIVER_LICENSE",
        "MEDICAL_LICENSE",
        "UK_NHS",
        "AU_ABN",
        "AU_ACN",
        "AU_TFN",
        "AU_MEDICARE",
    ]

    def __init__(
        self,
        entity_types: list[str] | None = None,
        allow_frontier_with_redaction: bool = False,
    ):
        """
        Initialize PII Shield.

        Args:
            entity_types: List of PII entity types to detect (defaults to DEFAULT_ENTITY_TYPES)
            allow_frontier_with_redaction: If True, allow frontier models with redacted text
        """
        self.entity_types = entity_types or self.DEFAULT_ENTITY_TYPES
        self.allow_frontier_with_redaction = allow_frontier_with_redaction

        # Initialize Presidio engines
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

        logger.info(
            "PII Shield initialized",
            entity_types=len(self.entity_types),
            allow_frontier_with_redaction=self.allow_frontier_with_redaction,
        )

    async def analyze(self, text: str) -> PIIResult:
        """
        Analyze text for PII and generate redacted version.

        Args:
            text: Input text to analyze

        Returns:
            PIIResult with detection results, redacted text, and routing directive
        """
        if not text or not text.strip():
            return PIIResult(
                original_text=text,
                pii_detected=False,
                pii_types=[],
                redacted_text=text,
                routing_directive=RoutingDirective.NO_RESTRICTION,
            )

        try:
            # Analyze text for PII (Presidio en recognizers + CN regex layer)
            analyzer_results = list(
                self.analyzer.analyze(
                    text=text,
                    entities=self.entity_types,
                    language="en",
                )
            )
            analyzer_results.extend(_cn_recognizer_results(text))

            pii_detected = len(analyzer_results) > 0
            pii_types = list({result.entity_type for result in analyzer_results})

            # Anonymize/redact PII
            if pii_detected:
                anonymizer_result = self.anonymizer.anonymize(
                    text=text,
                    # analyzer vs anonymizer ship distinct RecognizerResult
                    # classes with identical shape — same objects at runtime.
                    analyzer_results=analyzer_results,  # type: ignore[arg-type]
                )
                redacted_text = anonymizer_result.text
            else:
                redacted_text = text

            # Determine routing directive
            routing_directive = self._determine_routing(pii_detected)

            # Build entity details for logging
            pii_entities = [
                {
                    "entity_type": result.entity_type,
                    "start": result.start,
                    "end": result.end,
                    "score": result.score,
                }
                for result in analyzer_results
            ]

            logger.info(
                "PII analysis complete",
                pii_detected=pii_detected,
                pii_types=pii_types,
                pii_count=len(pii_entities),
                routing_directive=routing_directive.value,
            )

            return PIIResult(
                original_text=text,
                pii_detected=pii_detected,
                pii_types=pii_types,
                redacted_text=redacted_text,
                routing_directive=routing_directive,
                pii_entities=pii_entities,
            )

        except Exception as e:
            logger.error("PII analysis failed", error=str(e))
            # On error, be conservative and force local model
            return PIIResult(
                original_text=text,
                pii_detected=True,
                pii_types=["analysis_error"],
                redacted_text=text,
                routing_directive=RoutingDirective.LOCAL_MODEL_ONLY,
            )

    def _determine_routing(self, pii_detected: bool) -> RoutingDirective:
        """
        Determine routing directive based on PII detection and configuration.

        Args:
            pii_detected: Whether PII was detected

        Returns:
            RoutingDirective
        """
        if not pii_detected:
            return RoutingDirective.NO_RESTRICTION

        # PII detected
        if self.allow_frontier_with_redaction:
            return RoutingDirective.REDACTED_FRONTIER_OK
        else:
            return RoutingDirective.LOCAL_MODEL_ONLY


# Global instance for convenience
_pii_shield: PIIShield | None = None


def get_pii_shield() -> PIIShield:
    """Get or create global PII Shield instance."""
    global _pii_shield
    if _pii_shield is None:
        from desk.config import get_settings

        settings = get_settings()
        _pii_shield = PIIShield(
            allow_frontier_with_redaction=settings.pii_frontier_allowed_with_redaction,
        )
    return _pii_shield
