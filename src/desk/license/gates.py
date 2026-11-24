"""
ODW.ai Desk — License feature-gate dependencies (audit #11).

LicenseManager previously had zero callers: feature gates were dead library
code and every paid feature was usable on the default free license. These
dependencies enforce gates on paid surfaces when LICENSE_ENFORCEMENT_ENABLED
is set. Default off so existing free-tier dev/test deployments keep working;
operators enable enforcement explicitly.
"""

from collections.abc import Callable

import structlog
from fastapi import HTTPException

from desk.config import get_settings
from desk.db import AsyncSessionLocal
from desk.license.manager import FeatureGate, LicenseManager

logger = structlog.get_logger()


def require_feature(feature: FeatureGate) -> Callable[..., object]:
    """
    FastAPI dependency enforcing a license feature gate.

    No-op unless ``LICENSE_ENFORCEMENT_ENABLED=true``. When enabled, loads and
    revalidates the license (expiry/grace) and denies with 402 when the current
    tier does not include the feature.
    """

    async def dependency() -> None:
        settings = get_settings()
        if not settings.license_enforcement_enabled:
            return
        async with AsyncSessionLocal() as db:
            manager = LicenseManager(db)
            await manager.initialize()
            await manager.validate_license()
            allowed = manager.check_feature_gate(feature)
        if not allowed:
            logger.info("Feature gate denied", feature=feature.value)
            raise HTTPException(
                status_code=402,
                detail=f"Feature '{feature.value}' requires a higher license tier",
            )

    return dependency
