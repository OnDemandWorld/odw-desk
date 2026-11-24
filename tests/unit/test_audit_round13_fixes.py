"""
Regression tests for full-audit round 1, batch 13 (.ocr-reports/full-audit.json).

Covers:
- #41 customer resolver conflict re-read (now reachable via unique indexes)
- #51 OTLP export runs off the event loop
- #52 span ids are 16 hex chars (OTLP spec)
(#40 SQL window filter and #63 image/CI model provisioning are verified by
the existing suite + migration/CI inspection respectively.)
"""

import threading
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.exc import IntegrityError


class TestCustomerConflictReread:
    """#41: losing the insert race re-reads the winner instead of 500ing."""

    async def test_integrity_error_rereads_winner(self) -> None:
        from desk.router.customer_resolver import CustomerResolver

        winner = MagicMock()
        winner.id = uuid4()
        miss = MagicMock()
        miss.scalars.return_value.first.return_value = None
        hit = MagicMock()
        hit.scalars.return_value.first.return_value = winner
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[miss, hit])
        db.flush = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("dup")))
        db.rollback = AsyncMock()
        db.add = MagicMock()

        resolver = CustomerResolver(db)
        customer = await resolver.resolve_or_create("whatsapp", "+123")
        assert customer is winner
        db.rollback.assert_awaited_once()


class TestSpanIdSpec:
    """#52: OTLP span ids must be 8 bytes (16 hex chars)."""

    def test_span_id_length(self) -> None:
        from desk.observability.tracing import new_span_id, new_trace_id

        assert len(new_span_id()) == 16
        assert len(new_trace_id()) == 32  # trace ids stay 16 bytes


class TestOtlpExportOffLoop:
    """#51: export must not run synchronous HTTP on the caller's thread."""

    def test_export_spawns_thread_instead_of_blocking(self) -> None:
        import httpx

        from desk.observability.tracing import OtlpHttpSpanExporter, Span

        post = MagicMock()
        thread_cls = MagicMock()
        span = Span(name="op", trace_id="t", span_id="s", sampled=True)
        span.end_time = span.start_time + 1.0
        with (
            patch.object(httpx, "post", post),
            patch.object(threading, "Thread", thread_cls),
        ):
            OtlpHttpSpanExporter("http://collector:4318/v1/traces").export(span)
        post.assert_not_called()  # no synchronous HTTP on the event loop
        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs.get("daemon") is True
        thread_cls.return_value.start.assert_called_once()
