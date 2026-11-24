"""
ODW.ai Desk — License Manager (AGENT-006)

Validates license keys, enforces feature gates between free and paid tiers,
and manages grace periods.
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.config import get_settings
from desk.models.license_state import LicenseState

logger = structlog.get_logger()

# Values stored in / read from LicenseState.status (see the model's comment).
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_GRACE_PERIOD = "grace_period"
STATUS_INVALID = "invalid"


class LicenseTier(StrEnum):
    """License tier levels."""

    FREE = "free"
    PAID = "paid"
    ENTERPRISE = "enterprise"


class FeatureGate(StrEnum):
    """Feature gate identifiers."""

    # Free tier features
    WHATSAPP_BUSINESS = "whatsapp_business"
    BASIC_CHANNELS = "basic_channels"
    AI_AUTO_RESPONSE = "ai_auto_response"
    SINGLE_AGENT = "single_agent"

    # Paid tier features
    MULTI_AGENT = "multi_agent"
    ADVANCED_AI = "advanced_ai"
    COMPLIANCE_TOOLS = "compliance_tools"
    CUSTOM_PERSONA = "custom_persona"
    RESPONSE_POLICIES = "response_policies"

    # Enterprise tier features
    UNLIMITED_AGENTS = "unlimited_agents"
    PRIORITY_SUPPORT = "priority_support"
    CUSTOM_INTEGRATIONS = "custom_integrations"
    ADVANCED_ANALYTICS = "advanced_analytics"


# Feature gate mapping by tier
TIER_FEATURES = {
    LicenseTier.FREE: {
        FeatureGate.WHATSAPP_BUSINESS,
        FeatureGate.BASIC_CHANNELS,
        FeatureGate.AI_AUTO_RESPONSE,
        FeatureGate.SINGLE_AGENT,
    },
    LicenseTier.PAID: {
        FeatureGate.WHATSAPP_BUSINESS,
        FeatureGate.BASIC_CHANNELS,
        FeatureGate.AI_AUTO_RESPONSE,
        FeatureGate.SINGLE_AGENT,
        FeatureGate.MULTI_AGENT,
        FeatureGate.ADVANCED_AI,
        FeatureGate.COMPLIANCE_TOOLS,
        FeatureGate.CUSTOM_PERSONA,
        FeatureGate.RESPONSE_POLICIES,
    },
    LicenseTier.ENTERPRISE: {
        # All paid features plus enterprise features
        FeatureGate.WHATSAPP_BUSINESS,
        FeatureGate.BASIC_CHANNELS,
        FeatureGate.AI_AUTO_RESPONSE,
        FeatureGate.SINGLE_AGENT,
        FeatureGate.MULTI_AGENT,
        FeatureGate.ADVANCED_AI,
        FeatureGate.COMPLIANCE_TOOLS,
        FeatureGate.CUSTOM_PERSONA,
        FeatureGate.RESPONSE_POLICIES,
        FeatureGate.UNLIMITED_AGENTS,
        FeatureGate.PRIORITY_SUPPORT,
        FeatureGate.CUSTOM_INTEGRATIONS,
        FeatureGate.ADVANCED_ANALYTICS,
    },
}


class LicenseManager:
    """
    License Manager for validating licenses and enforcing feature gates.

    Supports online and offline license validation with grace periods.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self._license_state: LicenseState | None = None

    async def initialize(self) -> None:
        """Initialize license state from database or create default."""
        query = select(LicenseState).limit(1)
        result = await self.db.execute(query)
        self._license_state = result.scalar_one_or_none()

        if not self._license_state:
            # Create default free tier license
            now = datetime.now(tz=UTC)
            self._license_state = LicenseState(
                license_key=self.settings.license_key,
                tier=LicenseTier.FREE.value,
                status=STATUS_ACTIVE,
                valid_until=now + timedelta(days=36500),  # ~100 years
                grace_period_ends=now + timedelta(
                    days=36500 + self.settings.license_grace_period_days
                ),
                features={f.value: True for f in TIER_FEATURES[LicenseTier.FREE]},
                last_validated_at=now,
            )
            self.db.add(self._license_state)
            await self.db.commit()
            logger.info("Default free tier license created")
        else:
            logger.info(
                "License state loaded",
                tier=self._license_state.tier,
                status=self._license_state.status,
            )

    async def validate_license(self) -> bool:
        """
        Validate the current license.

        Checks expiration and grace period. Updates license state.
        """
        if not self._license_state:
            await self.initialize()

        assert self._license_state is not None

        now = datetime.now(tz=UTC)

        # Audit #49: a NULL valid_until is NOT perpetual validity — treat it
        # as invalid (previously such rows skipped all expiry logic and were
        # reset to ACTIVE).
        if self._license_state.valid_until is None:
            self._license_state.status = STATUS_EXPIRED
            self._license_state.last_validated_at = now
            await self.db.commit()
            logger.warning("License has no valid_until — treated as expired")
            return False

        # Check if license is expired
        if now > self._license_state.valid_until:
            # Check grace period
            grace_end = self._license_state.grace_period_ends or self._license_state.valid_until
            if now > grace_end:
                # Grace period expired
                self._license_state.status = STATUS_EXPIRED
                self._license_state.last_validated_at = now
                await self.db.commit()
                logger.warning("License expired and grace period ended")
                return False
            # In grace period
            if self._license_state.status != STATUS_GRACE_PERIOD:
                self._license_state.status = STATUS_GRACE_PERIOD
                self._license_state.last_validated_at = now
                await self.db.commit()
            logger.warning(
                "License expired, in grace period",
                grace_end=grace_end.isoformat(),
            )
            return True

        # License is valid
        if self._license_state.status != STATUS_ACTIVE:
            self._license_state.status = STATUS_ACTIVE
            self._license_state.last_validated_at = now
            await self.db.commit()

        return True

    def check_feature_gate(self, feature: FeatureGate) -> bool:
        """
        Check if a feature is allowed by the current license tier.

        Args:
            feature: Feature gate to check

        Returns:
            True if feature is allowed, False otherwise
        """
        if not self._license_state:
            logger.error("License state not initialized")
            return False

        if self._license_state.status not in (STATUS_ACTIVE, STATUS_GRACE_PERIOD):
            logger.warning(
                "License invalid, feature denied",
                feature=feature.value,
                status=self._license_state.status,
            )
            return False

        # Audit #49: re-check expiry directly — the cached status string alone
        # kept expired licenses passing gates until something revalidated.
        now = datetime.now(tz=UTC)
        valid_until = self._license_state.valid_until
        if valid_until is None:
            return False
        grace_end = self._license_state.grace_period_ends or valid_until
        if now > grace_end:
            logger.warning("License expired, feature denied", feature=feature.value)
            return False

        tier = LicenseTier(self._license_state.tier)
        allowed_features = TIER_FEATURES.get(tier, set())

        return feature in allowed_features

    def get_tier(self) -> LicenseTier:
        """Get the current license tier."""
        if not self._license_state:
            return LicenseTier.FREE
        return LicenseTier(self._license_state.tier)

    async def activate_license(self, license_key: str) -> dict[str, Any]:
        """
        Activate a new license key.

        In production, this would validate against a license server.
        For MVP, accepts any key and sets tier based on key format.
        """
        # Audit #48: keys must be HMAC-signed with the operator's activation
        # secret — format "<tier>.<expiry_iso8601>.<hmac-sha256-hex>" where the
        # signature covers "<tier>.<expiry_iso8601>". Previously the literal
        # strings 'paid'/'enterprise' granted those tiers with no validation.
        secret = self.settings.license_activation_secret
        if not secret:
            raise ValueError(
                "License activation unavailable: LICENSE_ACTIVATION_SECRET not configured"
            )
        # Split from the right: the ISO expiry may itself contain '.'
        # (fractional seconds), while the hex signature never does.
        rest, dot, signature = license_key.rpartition(".")
        tier_str, dot2, expiry_str = rest.partition(".")
        if not dot or not dot2:
            raise ValueError("Invalid license key format (expected tier.expiry.signature)")
        expected = hmac.new(
            secret.encode(), f"{tier_str}.{expiry_str}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid license key signature")
        try:
            tier = LicenseTier(tier_str)
        except ValueError as exc:
            raise ValueError(f"Unknown license tier '{tier_str}'") from exc
        try:
            expiry = datetime.fromisoformat(expiry_str)
        except ValueError as exc:
            raise ValueError("Invalid license expiry (expected ISO 8601)") from exc
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)

        if not self._license_state:
            await self.initialize()

        assert self._license_state is not None

        now = datetime.now(tz=UTC)
        if expiry <= now:
            raise ValueError("License key already expired")
        self._license_state.license_key = license_key
        self._license_state.tier = tier.value
        self._license_state.status = STATUS_ACTIVE
        self._license_state.valid_until = expiry
        self._license_state.grace_period_ends = expiry + timedelta(
            days=self.settings.license_grace_period_days
        )
        self._license_state.features = {f.value: True for f in TIER_FEATURES[tier]}
        self._license_state.last_validated_at = now

        await self.db.commit()

        logger.info("License activated", tier=tier.value, key=license_key[:10])

        assert self._license_state.valid_until is not None
        return {
            "success": True,
            "tier": tier.value,
            "expires_at": self._license_state.valid_until.isoformat(),
        }

    async def get_license_info(self) -> dict[str, Any]:
        """Get current license information."""
        if not self._license_state:
            await self.initialize()

        assert self._license_state is not None

        tier = LicenseTier(self._license_state.tier)
        allowed_features = TIER_FEATURES.get(tier, set())

        return {
            "license_key": self._license_state.license_key,
            "tier": tier.value,
            "status": self._license_state.status,
            "is_valid": self._license_state.status in (STATUS_ACTIVE, STATUS_GRACE_PERIOD),
            "activated_at": (
                self._license_state.created_at.isoformat()
                if self._license_state.created_at
                else None
            ),
            "expires_at": (
                self._license_state.valid_until.isoformat()
                if self._license_state.valid_until
                else None
            ),
            "grace_period_ends": (
                self._license_state.grace_period_ends.isoformat()
                if self._license_state.grace_period_ends
                else None
            ),
            "allowed_features": [f.value for f in allowed_features],
            "features": self._license_state.features,
        }
