"""
ODW.ai Desk — License Manager (AGENT-006)

Validates license keys, enforces feature gates between free and paid tiers,
and manages grace periods.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from desk.config import get_settings
from desk.models.license_state import LicenseState

logger = structlog.get_logger()


class LicenseTier(str, Enum):
    """License tier levels."""

    FREE = "free"
    PAID = "paid"
    ENTERPRISE = "enterprise"


class FeatureGate(str, Enum):
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
            self._license_state = LicenseState(
                license_key=self.settings.license_key,
                tier=LicenseTier.FREE.value,
                is_valid=True,
                activated_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=36500),  # ~100 years
                grace_period_days=self.settings.license_grace_period_days,
                metadata_={"auto_generated": True},
            )
            self.db.add(self._license_state)
            await self.db.commit()
            logger.info("Default free tier license created")
        else:
            logger.info(
                "License state loaded",
                tier=self._license_state.tier,
                is_valid=self._license_state.is_valid,
            )

    async def validate_license(self) -> bool:
        """
        Validate the current license.

        Checks expiration and grace period. Updates license state.
        """
        if not self._license_state:
            await self.initialize()

        assert self._license_state is not None

        now = datetime.utcnow()

        # Check if license is expired
        if self._license_state.expires_at and now > self._license_state.expires_at:
            # Check grace period
            grace_end = self._license_state.expires_at + timedelta(
                days=self._license_state.grace_period_days or 0
            )
            if now > grace_end:
                # Grace period expired
                self._license_state.is_valid = False
                await self.db.commit()
                logger.warning("License expired and grace period ended")
                return False
            else:
                # In grace period
                logger.warning(
                    "License expired, in grace period",
                    grace_end=grace_end.isoformat(),
                )
                return True

        # License is valid
        if not self._license_state.is_valid:
            self._license_state.is_valid = True
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

        if not self._license_state.is_valid:
            logger.warning("License invalid, feature denied", feature=feature.value)
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
        # Simple key format: "free", "paid", "enterprise"
        tier = LicenseTier.FREE
        if license_key.lower() == "paid":
            tier = LicenseTier.PAID
        elif license_key.lower() == "enterprise":
            tier = LicenseTier.ENTERPRISE

        if not self._license_state:
            await self.initialize()

        assert self._license_state is not None

        self._license_state.license_key = license_key
        self._license_state.tier = tier.value
        self._license_state.is_valid = True
        self._license_state.activated_at = datetime.utcnow()
        self._license_state.expires_at = datetime.utcnow() + timedelta(days=365)

        await self.db.commit()

        logger.info("License activated", tier=tier.value, key=license_key[:10])

        return {
            "success": True,
            "tier": tier.value,
            "expires_at": self._license_state.expires_at.isoformat(),
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
            "is_valid": self._license_state.is_valid,
            "activated_at": self._license_state.activated_at.isoformat() if self._license_state.activated_at else None,
            "expires_at": self._license_state.expires_at.isoformat() if self._license_state.expires_at else None,
            "grace_period_days": self._license_state.grace_period_days,
            "allowed_features": [f.value for f in allowed_features],
            "metadata": self._license_state.metadata_,
        }
