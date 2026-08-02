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

import random
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from desk.config import get_settings

logger = structlog.get_logger()

# Header used to propagate the trace id across services (see INTEGRATION_CONTRACT).
TRACE_HEADER = "X-Trace-Id"

# structlog context key the trace id is bound under.
TRACE_CONTEXT_KEY = "trace_id"


def new_trace_id() -> str:
    """Generate a fresh trace id (UUID4 hex)."""
    return uuid.uuid4().hex


def new_span_id() -> str:
    """Generate a fresh span id (UUID4 hex)."""
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


# ---------------------------------------------------------------------------
# V1.6 F-2 — Span model + sampling + export (DS1/DS2)
#
# A lightweight span tree layered on the V1.5 trace_id. ``start_span`` pushes a
# span onto a per-context stack; nested spans auto-parent from the current top
# and inherit the active trace_id. Sampling (``TRACE_SAMPLE_RATE``) decides at
# the root whether a tree is recorded — unsampled spans are no-ops that never
# export. Export is best-effort and never raises into the caller.
# ---------------------------------------------------------------------------

# Per-context span stack. The root of a tree is the first element; the active
# span is the last. Kept separate from the structlog trace_id context so span
# nesting does not interfere with log correlation.
_span_stack: ContextVar[list["Span"] | None] = ContextVar("_span_stack", default=None)


def _current_span() -> "Span | None":
    """Return the active (innermost) span in this context, if any."""
    stack = _span_stack.get()
    return stack[-1] if stack else None


def _should_sample() -> bool:
    """Decide whether a new root trace should be sampled (TRACE_SAMPLE_RATE)."""
    rate = get_settings().trace_sample_rate
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


@dataclass
class Span:
    """
    A single unit of timed work within a trace.

    Sampled spans record start/end times and are handed to the configured
    exporter on :meth:`end`. Unsampled spans are no-ops: they still parent
    children and track timing, but never export.
    """

    name: str
    trace_id: str
    span_id: str
    parent_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    sampled: bool = True
    _ended: bool = False

    @property
    def duration_ms(self) -> float | None:
        """Elapsed wall-clock time in milliseconds, or None if not ended."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def set_attribute(self, key: str, value: Any) -> "Span":
        """Attach a key/value attribute to the span (chainable)."""
        self.attributes[key] = value
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize the span for export/logging."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "sampled": self.sampled,
            "attributes": self.attributes,
        }

    def end(self, status: str = "ok") -> None:
        """
        Finish the span, pop it from the stack, and export it (best-effort).

        Idempotent: ending an already-ended span is a no-op. Unsampled spans
        are popped but never exported. Export failures never propagate.
        """
        if self._ended:
            return
        self._ended = True
        self.end_time = time.time()
        self.status = status

        stack = _span_stack.get()
        if stack and self in stack:
            stack.remove(self)

        if self.sampled:
            try:
                exporter = get_span_exporter()
                if exporter is not None:
                    exporter.export(self)
            except Exception as exc:  # noqa: BLE001 - export must never raise
                logger.debug("Span export failed (best-effort)", error=str(exc))

    # Context-manager support: ``with start_span("op") as span:`` — works inside
    # async functions too (spans time wall-clock and never await).
    def __enter__(self) -> "Span":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.end(status="error" if exc_type is not None else "ok")


def start_span(name: str, attrs: dict[str, Any] | None = None, trace_id: str | None = None) -> Span:
    """
    Start a new span and push it onto the current context's span stack.

    Child spans auto-parent from the active span and inherit its trace_id and
    sampling decision. A root span (no parent) resolves its trace_id from the
    bound structlog ``trace_id`` (V1.5 propagation) or generates a fresh one,
    and makes the sampling decision via ``TRACE_SAMPLE_RATE``.

    Best-effort: never raises. Returns the active (sampled or no-op) span.
    """
    parent = _current_span()
    if parent is not None:
        span_trace_id = parent.trace_id
        sampled = parent.sampled  # inherit the root's sampling decision
        parent_id = parent.span_id
    else:
        span_trace_id = trace_id or get_current_trace_id() or new_trace_id()
        sampled = _should_sample()
        parent_id = None

    span = Span(
        name=name,
        trace_id=span_trace_id,
        span_id=new_span_id(),
        parent_id=parent_id,
        attributes=dict(attrs or {}),
        sampled=sampled,
    )

    stack = _span_stack.get()
    if stack is None:
        stack = []
        _span_stack.set(stack)
    stack.append(span)
    return span


# ---------------------------------------------------------------------------
# Exporters (DS2)
# ---------------------------------------------------------------------------


class ConsoleSpanExporter:
    """Default exporter: emits finished spans through structlog."""

    def export(self, span: Span) -> None:
        logger.info(
            "span",
            name=span.name,
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_id=span.parent_id,
            duration_ms=span.duration_ms,
            status=span.status,
            attributes=span.attributes,
        )


class OtlpHttpSpanExporter:
    """
    Best-effort OTLP/HTTP exporter.

    POSTs a minimal OTLP-shaped JSON payload to ``OTLP_ENDPOINT``. Any failure
    (no endpoint, connection error, non-2xx) is logged at debug and swallowed so
    tracing never disrupts the request path.
    """

    def __init__(self, endpoint: str, timeout: float = 2.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def _payload(self, span: Span) -> dict[str, Any]:
        attributes = [
            {"key": key, "value": {"string_value": str(value)}}
            for key, value in span.attributes.items()
        ]
        return {
            "resourceSpans": [
                {
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": span.trace_id,
                                    "spanId": span.span_id,
                                    "parentSpanId": span.parent_id or "",
                                    "name": span.name,
                                    "startTimeUnixNano": int(span.start_time * 1e9),
                                    "endTimeUnixNano": int((span.end_time or span.start_time) * 1e9),
                                    "attributes": attributes,
                                }
                            ]
                        }
                    ]
                }
            ]
        }

    def export(self, span: Span) -> None:
        if not self.endpoint:
            return
        try:
            import httpx

            httpx.post(self.endpoint, json=self._payload(span), timeout=self.timeout)
        except Exception as exc:  # noqa: BLE001 - best-effort, silent degradation
            logger.debug("OTLP span export failed (best-effort)", error=str(exc))


def get_span_exporter() -> ConsoleSpanExporter | OtlpHttpSpanExporter | None:
    """
    Resolve the configured span exporter (TRACE_EXPORTER).

    ``console`` (default) logs via structlog, ``otlp`` POSTs best-effort to
    ``OTLP_ENDPOINT``, and ``none`` disables export.
    """
    settings = get_settings()
    kind = settings.trace_exporter
    if kind == "none":
        return None
    if kind == "otlp":
        return OtlpHttpSpanExporter(settings.otlp_endpoint)
    return ConsoleSpanExporter()
