"""
ODW.ai Desk — Role-Based Access Control (RBAC)

Enables the previously unused ``role`` concept for the admin and agent inbox
routers. Two roles are modelled, ordered by privilege:

    agent  <  admin

``require_role(min_role)`` is a FastAPI dependency factory:
- ``/api/v1/admin/*``  -> ``require_role("admin")``
- ``/api/v1/agents/*`` -> ``require_role("agent")``  (agent or above)

Backward compatibility (mirrors ``desk.security.api_auth``):
- When ``DESK_API_KEY`` is unset/empty the dependency is a no-op and the routes
  stay open (dev / existing tests).
- When set, the request must first authenticate (same key rules as
  ``require_api_key``) and then present a sufficient role.

Role resolution for an authenticated principal (in priority order):
1. ``role`` claim of a JWT bearer token (HS256, signed with ``settings.secret_key``).
2. The explicit ``X-Desk-Role`` header (``admin`` / ``agent``).
3. ``settings.desk_default_role`` (defaults to ``admin`` for dev single-user).
"""

import hmac
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import Header, HTTPException
from jose import JWTError, jwt

from desk.config import Settings, get_settings

logger = structlog.get_logger()

# Privilege levels: a principal satisfies a requirement when its level is >= the
# required level. Unknown roles resolve to 0 and therefore fail every guard.
ROLE_LEVELS: dict[str, int] = {
    "agent": 1,
    "admin": 2,
}


def _role_from_jwt(token: str, settings: Settings) -> str | None:
    """
    Best-effort extraction of a ``role`` claim from a JWT bearer token.

    Returns None when the token is not a valid JWT (e.g. it is a raw API key
    presented as a bearer token) or carries no recognised role claim.
    """
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        return None

    role = claims.get("role")
    if isinstance(role, str) and role.lower() in ROLE_LEVELS:
        return role.lower()
    return None


def resolve_role(
    settings: Settings,
    authorization: str | None = None,
    desk_role: str | None = None,
) -> str:
    """
    Resolve the effective role for an authenticated principal.

    Priority: JWT ``role`` claim > ``X-Desk-Role`` header > configured default.
    """
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            jwt_role = _role_from_jwt(token.strip(), settings)
            if jwt_role:
                return jwt_role

    if desk_role and desk_role.strip().lower() in ROLE_LEVELS:
        return desk_role.strip().lower()

    return settings.desk_default_role


def require_role(min_role: str) -> Callable[..., Any]:
    """
    FastAPI dependency factory enforcing a minimum role on a router/route.

    Args:
        min_role: Minimum required role ("agent" or "admin").

    Returns:
        An async dependency that yields the resolved role, or None when no API
        key is configured (routes stay open).

    Raises:
        HTTPException: 401 when a key is configured and not presented/matched;
            403 when authenticated but the role is insufficient.
    """
    required_level = ROLE_LEVELS.get(min_role, 0)

    async def dependency(
        x_api_key: str | None = Header(None, alias="X-API-Key"),
        authorization: str | None = Header(None, alias="Authorization"),
        desk_role: str | None = Header(None, alias="X-Desk-Role"),
    ) -> str | None:
        settings = get_settings()
        expected_key = settings.desk_api_key

        # No key configured -> routes stay open (backward compatible).
        if not expected_key:
            return None

        # Authenticate via one of two principals:
        # 1. A valid JWT bearer token (authenticated by its signature; role from
        #    its ``role`` claim).
        # 2. The shared API key (X-API-Key header, or a non-JWT bearer token),
        #    matching ``require_api_key``; role from header/configured default.
        bearer_token: str | None = None
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token.strip():
                bearer_token = token.strip()

        jwt_role = _role_from_jwt(bearer_token, settings) if bearer_token else None

        if jwt_role is not None:
            role = jwt_role
        else:
            provided = x_api_key or bearer_token
            # compare_digest requires ASCII-only str; encode so non-ASCII
            # input produces a 401 instead of an unhandled TypeError (500).
            if (
                not provided
                or not hmac.compare_digest(
                    provided.encode("utf-8"), expected_key.encode("utf-8")
                )
            ):
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
            role = resolve_role(settings, desk_role=desk_role)

        # Authorize: compare privilege levels.
        if ROLE_LEVELS.get(role, 0) < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' insufficient; requires '{min_role}'",
            )

        return role

    return dependency
