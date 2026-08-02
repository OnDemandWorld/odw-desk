"""
ODW.ai Desk — Unit Tests for Tracing Spans (V1.6 F-2, DS1/DS2/DS3)

Covers the span tree/parenting + sampling + no-op behaviour (DS1), the console
and best-effort OTLP exporters (DS2), and that the AI engine emits an
``ai.process`` span (DS3). Spans/export are best-effort: sampling defaults to
1.0, the exporter to console, and nothing here may raise into the caller.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import structlog
from structlog.testing import capture_logs

from desk.ai.engine import AIEngine
from desk.config import get_settings
from desk.observability.tracing import (
    ConsoleSpanExporter,
    OtlpHttpSpanExporter,
    Span,
    get_span_exporter,
    start_span,
)


def _spans(cap_logs):
    """Filter captured structlog entries down to exported span records."""
    return [e for e in cap_logs if e.get("event") == "span"]


class TestSpanModel:
    def test_duration_none_until_ended(self):
        span = Span(name="op", trace_id="t", span_id="s")
        assert span.duration_ms is None
        span.end_time = span.start_time + 1.0
        assert span.duration_ms == pytest.approx(1000.0)

    def test_to_dict_serializes_fields(self):
        span = Span(name="op", trace_id="t", span_id="s", parent_id="p")
        span.set_attribute("k", "v")
        data = span.to_dict()
        assert data["name"] == "op"
        assert data["trace_id"] == "t"
        assert data["parent_id"] == "p"
        assert data["attributes"] == {"k": "v"}

    def test_end_is_idempotent(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        span = start_span("op")
        span.end()
        first_end = span.end_time
        span.end()  # second call is a no-op
        assert span.end_time == first_end


class TestSpanTreeParenting:
    def test_child_auto_parents_from_active_span(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        root = start_span("root")
        child = start_span("child")
        grandchild = start_span("grandchild")

        assert root.parent_id is None
        assert child.parent_id == root.span_id
        assert grandchild.parent_id == child.span_id
        # The whole tree shares the root's trace id.
        assert child.trace_id == root.trace_id
        assert grandchild.trace_id == root.trace_id

        grandchild.end()
        child.end()
        root.end()

        # Stack drained — a new span starts a fresh root.
        new_root = start_span("new_root")
        assert new_root.parent_id is None
        new_root.end()

    def test_root_span_uses_bound_structlog_trace_id(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        structlog.contextvars.bind_contextvars(trace_id="bound-trace")
        try:
            span = start_span("op")
            assert span.trace_id == "bound-trace"
            assert span.parent_id is None
            span.end()
        finally:
            structlog.contextvars.unbind_contextvars("trace_id")

    def test_explicit_trace_id_wins_for_root(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        span = start_span("op", trace_id="explicit-trace")
        assert span.trace_id == "explicit-trace"
        span.end()

    def test_context_manager_sets_error_status(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        with pytest.raises(RuntimeError):
            with start_span("op") as span:
                raise RuntimeError("boom")
        assert span.status == "error"
        assert span._ended is True

    def test_context_manager_ok_status_on_success(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        with start_span("op") as span:
            pass
        assert span.status == "ok"


class TestSampling:
    def test_rate_one_samples_everything(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_sample_rate", 1.0)
        span = start_span("op")
        assert span.sampled is True
        span.end()

    def test_rate_zero_yields_unsampled_noop(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_sample_rate", 0.0)
        monkeypatch.setattr(get_settings(), "trace_exporter", "console")
        with capture_logs() as cap:
            span = start_span("op")
            assert span.sampled is False
            span.end()
        # Unsampled spans never export.
        assert _spans(cap) == []

    def test_child_inherits_unsampled_root(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_sample_rate", 0.0)
        root = start_span("root")
        child = start_span("child")
        assert root.sampled is False
        assert child.sampled is False
        child.end()
        root.end()


class TestConsoleExporter:
    def test_emits_structlog_record(self):
        span = Span(name="op", trace_id="t1", span_id="s1", sampled=True)
        span.end_time = span.start_time + 0.5
        with capture_logs() as cap:
            ConsoleSpanExporter().export(span)
        entries = _spans(cap)
        assert len(entries) == 1
        assert entries[0]["name"] == "op"
        assert entries[0]["trace_id"] == "t1"
        assert entries[0]["duration_ms"] == pytest.approx(500.0)

    def test_span_end_exports_via_console(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "console")
        monkeypatch.setattr(get_settings(), "trace_sample_rate", 1.0)
        with capture_logs() as cap:
            span = start_span("op", {"k": "v"})
            span.end()
        entries = _spans(cap)
        assert len(entries) == 1
        assert entries[0]["name"] == "op"
        assert entries[0]["attributes"] == {"k": "v"}


class TestOtlpExporter:
    def test_posts_payload_to_endpoint(self, monkeypatch):
        post = MagicMock()
        monkeypatch.setattr(httpx, "post", post)
        span = Span(name="op", trace_id="t", span_id="s", parent_id="p", sampled=True)
        span.end_time = span.start_time + 1.0

        OtlpHttpSpanExporter("http://collector:4318/v1/traces").export(span)

        post.assert_called_once()
        args, kwargs = post.call_args
        assert args[0] == "http://collector:4318/v1/traces"
        otlp_span = kwargs["json"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        assert otlp_span["name"] == "op"
        assert otlp_span["traceId"] == "t"
        assert otlp_span["parentSpanId"] == "p"

    def test_empty_endpoint_is_noop(self, monkeypatch):
        post = MagicMock()
        monkeypatch.setattr(httpx, "post", post)
        OtlpHttpSpanExporter("").export(Span(name="o", trace_id="t", span_id="s"))
        post.assert_not_called()

    def test_failure_degrades_silently(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(httpx, "post", boom)
        span = Span(name="op", trace_id="t", span_id="s", sampled=True)
        span.end_time = span.start_time
        # Must not raise.
        OtlpHttpSpanExporter("http://collector:4318/v1/traces").export(span)

    def test_span_end_survives_otlp_failure(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "otlp")
        monkeypatch.setattr(get_settings(), "otlp_endpoint", "http://collector:4318/v1/traces")
        monkeypatch.setattr(httpx, "post", MagicMock(side_effect=RuntimeError("down")))
        span = start_span("op")
        span.end()  # no exception propagates


class TestExporterResolution:
    def test_console_default(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "console")
        assert isinstance(get_span_exporter(), ConsoleSpanExporter)

    def test_otlp(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "otlp")
        assert isinstance(get_span_exporter(), OtlpHttpSpanExporter)

    def test_none_disables_export(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        assert get_span_exporter() is None


class TestEngineProcessSpan:
    """DS3 — engine.process emits an ai.process span (best-effort)."""

    async def test_process_emits_ai_process_span(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "trace_exporter", "console")
        monkeypatch.setattr(get_settings(), "trace_sample_rate", 1.0)

        # Bypass the heavy __init__; force the first pipeline step to fail so the
        # method takes its safe-fallback path while still exercising the span.
        engine = AIEngine.__new__(AIEngine)
        engine.pii_shield = MagicMock()
        engine.pii_shield.analyze = AsyncMock(side_effect=RuntimeError("boom"))

        with capture_logs() as cap:
            result = await engine.process("conv-1", "hello", "webchat", "visitor-1")

        assert isinstance(result, str)  # fallback reply, behaviour unchanged
        entries = _spans(cap)
        assert any(e["name"] == "ai.process" for e in entries)
        ai_span = next(e for e in entries if e["name"] == "ai.process")
        assert ai_span["attributes"]["conversation_id"] == "conv-1"
        assert ai_span["attributes"]["channel"] == "webchat"

    async def test_process_span_does_not_alter_response(self, monkeypatch):
        """With export disabled, process still returns its normal fallback."""
        monkeypatch.setattr(get_settings(), "trace_exporter", "none")
        engine = AIEngine.__new__(AIEngine)
        engine.pii_shield = MagicMock()
        engine.pii_shield.analyze = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("desk.ai.engine.reply_language", return_value="en"):
            result = await engine.process("conv-1", "hello", "webchat", "visitor-1")
        assert isinstance(result, str)
