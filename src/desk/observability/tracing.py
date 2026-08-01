"""
ODW.ai Desk — Distributed Tracing (V1.5 F-3, DT1)

Best-effort request tracing. Every inbound HTTP request carries an
``X-Trace-Id``; when the caller does not supply one, a fresh UUID is generated.
The id is bound into the structlog context (``trace_id``) for the duration of
the request so all log lines emitted while handling it are correlatable, and it
is echoed back on the response. Outbound cross-product calls (e.g. Desk→Vault)
read the current id via :func:`get_current_trace_id` and forward it as a header.

This is purely additive: business responses are unchanged and, when no trace id
is present in the context, nothing extra is sent.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()

# Header used to propagate the trace id across services (see INTEGRATION_CONTRACT).
TRACE_HEADER = "X-Trace-Id"

# structlog context key the trace id is bound under.
TRACE_CONTEXT_KEY = "trace_id"


def new_trace_id() -> str:
    """Generate a fresh trace id (UUID4 hex)."""
    return uuid.uuid4().hex


def get_current_trace_id() -> str | None:
    """
    Return the trace id bound to the current context, if any.

    Used by outbound clients (e.g. ``vault_client``) to forward ``X-Trace-Id``
    best-effort. Returns None outside a traced request so callers send nothing.
    """
    return structlog.contextvars.get_contextvars().get(TRACE_CONTEXT_KEY)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """
    Bind an ``X-Trace-Id`` into the structlog context for each request.

    Reads the inbound ``X-Trace-Id`` header (generating a UUID when absent),
    binds it as ``trace_id`` for the duration of the request, echoes it back on
    the response, and clears it afterwards so it never leaks across requests.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or new_trace_id()
        structlog.contextvars.bind_contextvars(**{TRACE_CONTEXT_KEY: trace_id})
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars(TRACE_CONTEXT_KEY)
        response.headers[TRACE_HEADER] = trace_id
        return response
