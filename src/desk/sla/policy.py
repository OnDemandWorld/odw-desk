"""
ODW.ai Desk — SLA Policy

Builds SLA thresholds from application settings. Thresholds are expressed in
minutes so a single unit drives evaluation in :mod:`desk.sla.service`.
"""

from dataclasses import dataclass

from desk.config import Settings, get_settings


@dataclass(frozen=True)
class SLAPolicy:
    """SLA thresholds (in minutes) used to evaluate conversations."""

    first_response_minutes: int
    resolution_minutes: int

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "SLAPolicy":
        """
        Build a policy from application settings.

        The resolution threshold is derived from the existing
        ``sla_resolution_hours`` config field (converted to minutes) so the
        V1.0 configuration surface is reused unchanged — no new env vars are
        required and default behaviour is preserved.
        """
        settings = settings or get_settings()
        return cls(
            first_response_minutes=settings.sla_first_response_minutes,
            resolution_minutes=settings.sla_resolution_hours * 60,
        )
