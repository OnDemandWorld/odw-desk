"""
ODW.ai Desk — Unit Tests for Distributed Tracing (V1.5 F-3, DT1)

The TraceIdMiddleware reads X-Trace-Id (generating a UUID when absent), binds it
into the structlog context for the duration of the request, echoes it on the
response, and clears it afterwards so it never leaks across requests.
"""

from unittest.mock import MagicMock

import structlog
from fastapi.testclient import TestClient
from starlette.responses import Response

from desk.main import app
from desk.observability.tracing import (
    TRACE_HEADER,
    TraceIdMiddleware,
    get_current_trace_id,
)


def _middleware():
    return TraceIdMiddleware(MagicMock())


def _request_with_headers(headers: dict) -> MagicMock:
    request = MagicMock()
    request.headers = headers
    return request


class TestTraceIdMiddlewareDispatch:
    async def test_uses_inbound_trace_header(self):
        seen = {}

        async def call_next(_req):
            seen["during"] = get_current_trace_id()
            return Response("ok")

        mw = _middleware()
        response = await mw.dispatch(_request_with_headers({TRACE_HEADER: "trace-abc"}), call_next)

        # Bound while handling the request, echoed on the response.
        assert seen["during"] == "trace-abc"
        assert response.headers[TRACE_HEADER] == "trace-abc"
        # Cleared afterwards (no leak into the surrounding context).
        assert get_current_trace_id() is None

    async def test_generates_trace_id_when_header_absent(self):
        seen = {}

        async def call_next(_req):
            seen["during"] = get_current_trace_id()
            return Response("ok")

        mw = _middleware()
        response = await mw.dispatch(_request_with_headers({}), call_next)

        generated = seen["during"]
        assert generated  # a trace id was bound during the request
        assert len(generated) == 32  # uuid4 hex
        assert response.headers[TRACE_HEADER] == generated
        assert get_current_trace_id() is None

    async def test_clears_trace_id_even_when_handler_raises(self):
        async def call_next(_req):
            raise RuntimeError("boom")

        mw = _middleware()
        try:
            await mw.dispatch(_request_with_headers({TRACE_HEADER: "t1"}), call_next)
        except RuntimeError:
            pass
        # Context is cleared on the error path too.
        assert get_current_trace_id() is None


class TestTraceIdMiddlewareIntegration:
    """End-to-end header echo through the real FastAPI app."""

    def test_echoes_provided_trace_id(self):
        client = TestClient(app)
        response = client.get("/", headers={TRACE_HEADER: "req-trace-123"})
        assert response.status_code == 200
        assert response.headers[TRACE_HEADER] == "req-trace-123"

    def test_generates_trace_id_when_not_provided(self):
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers.get(TRACE_HEADER)  # present and non-empty


class TestGetCurrentTraceId:
    def test_returns_bound_value_and_clears(self):
        assert get_current_trace_id() is None
        structlog.contextvars.bind_contextvars(trace_id="bound-1")
        try:
            assert get_current_trace_id() == "bound-1"
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")
        assert get_current_trace_id() is None
