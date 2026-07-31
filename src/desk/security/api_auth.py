"""
ODW.ai Desk — Optional API Key Guard

Backward-compatible authentication guard for the admin and agent inbox routes.

Reads ``DESK_API_KEY`` (``settings.desk_api_key``):
- When unset/empty, the guard is a no-op and routes stay open (dev / existing tests).
- When set, requests to the guarded routers must present the key via the
  ``X-API-Key`` header or ``Authorization: Bearer <key>``; otherwise 401.

Health (``/health``) and webhooks (``/api/v1/webhooks/*``) are never guarded —
the guard is only applied to the admin and agent routers in ``main.py``.
"""

import hmac

import structlog
from fastapi import Header, HTTPException

from desk.config import get_settings

logger = structlog.get_logger()


async def require_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> None:
    """
    FastAPI dependency enforcing the optional Desk API key.

    Raises:
        HTTPException: 401 when a key is configured and the request does not
            present a matching key.
    """
    settings = get_settings()
    expected_key = settings.desk_api_key

    # No key configured -> routes stay open (backward compatible).
    if not expected_key:
        return

    provided = x_api_key
    if not provided and authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            provided = token.strip()

    if not provided or not hmac.compare_digest(provided, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
