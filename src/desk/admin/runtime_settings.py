"""
ODW.ai Desk — Runtime Settings (admin-configurable, DB-backed)

D-3/D-4 fix: the admin setup endpoints (`POST /setup/vault`, `POST /setup/whatsapp`,
`PUT /config/pii`, `POST /setup/ai-model`) previously logged and returned
`success: true` without persisting anything, and the runtime components only
ever read process-env settings. This module provides:

- a `system_settings` key/value table (durable across restarts),
- a process-local override cache for synchronous readers (VaultClient etc.),
- helpers used by the admin endpoints to persist + activate overrides.

Single-process semantics: the cache is per-process (fine for the self-hosted
single-node deployment; multi-worker deployments pick changes up after restart
or when each worker handles the write itself).
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from desk.models.base import Base, TimestampMixin

logger = structlog.get_logger()

# Process-local override cache: key → value. Refreshed from the DB at startup
# and updated in-place by the admin endpoints on write.
_overrides: dict[str, Any] = {}

# Cache TTL (seconds) for the AI runtime-config snapshot in the engine.
RUNTIME_CONFIG_TTL_SECONDS = 60


class SystemSetting(TimestampMixin, Base):
    """Durable admin-configured runtime override (key → JSON value)."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(primary_key=True, max_length=100)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SystemSetting(key={self.key!r})>"


def get_override(key: str) -> Any | None:
    """Synchronous read from the process-local override cache."""
    return _overrides.get(key)


def set_override(key: str, value: Any) -> None:
    """Update the process-local cache (call after a successful DB persist)."""
    _overrides[key] = value


async def persist(db, key: str, value: dict[str, Any]) -> None:
    """Upsert a setting row and refresh the process-local cache."""
    from sqlalchemy import select

    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalar_one_or_none()
    if row is None:
        row = SystemSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    set_override(key, value)
    logger.info("Runtime setting persisted", key=key)


async def load_all(db) -> dict[str, Any]:
    """Load every persisted setting into the process cache (startup)."""
    from sqlalchemy import select

    rows = (await db.execute(select(SystemSetting))).scalars().all()
    loaded = {row.key: row.value for row in rows}
    _overrides.clear()
    _overrides.update(loaded)
    if loaded:
        logger.info("Runtime settings loaded from database", keys=sorted(loaded.keys()))
    return dict(_overrides)


class TTLCache:
    """Minimal TTL cache used by the AI engine's runtime-config snapshot."""

    def __init__(self, ttl_seconds: float = RUNTIME_CONFIG_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._value: Any = None
        self._stamp: float = 0.0

    def get(self) -> Any | None:
        if self._value is None or (time.monotonic() - self._stamp) >= self._ttl:
            return None
        return self._value

    def put(self, value: Any) -> None:
        self._value = value
        self._stamp = time.monotonic()

    def invalidate(self) -> None:
        self._value = None
        self._stamp = 0.0
