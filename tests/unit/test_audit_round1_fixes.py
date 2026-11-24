"""
Regression tests for full-audit round 1 fixes (.ocr-reports/full-audit.json).

Covers:
- #10 rate limiter evicts expired attacker-controlled keys (memory DoS)
- #13 runtime-config apply failure falls back to local instead of halting AI
- #9  message processor uses a per-process consumer name (PEL attribution)
- #12 retention sweep helper invokes ComplianceEngine.enforce_retention_policy
"""

import asyncio
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from desk.channels.rate_limit import SlidingWindowRateLimiter


class TestRateLimiterKeyEviction:
    """#10: expired keys must not accumulate forever."""

    def test_expired_key_evicted_on_next_allow(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("visitor-a", now=100.0) is True
        assert "visitor-a" in limiter._events
        # Window fully expired: prune evicts, then the new event re-registers.
        assert limiter.allow("visitor-a", now=200.0) is True
        assert set(limiter._events) == {"visitor-a"}
        assert len(limiter._events["visitor-a"]) == 1

    def test_unique_visitors_do_not_accumulate(self) -> None:
        # Hard key cap: even with all keys active, memory stays bounded.
        limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60, max_keys=100)
        for i in range(500):
            assert limiter.allow(f"visitor-{i}", now=100.0) is True
        assert len(limiter._events) <= 100
        # Once the window expires, the cap-triggered sweep reclaims everything.
        assert limiter.allow("probe", now=200.0) is True
        assert set(limiter._events) == {"probe"}

    def test_amortized_sweep_reclaims_unrevisited_keys(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
        for i in range(1023):
            assert limiter.allow(f"visitor-{i}", now=100.0) is True
        assert len(limiter._events) == 1023
        # The 1024th allow triggers the periodic sweep; expired keys go away.
        assert limiter.allow("probe", now=200.0) is True
        assert set(limiter._events) == {"probe"}

    def test_remaining_does_not_create_keys(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        assert limiter.remaining("never-seen", now=100.0) == 5
        assert "never-seen" not in limiter._events

    def test_limit_still_enforced_within_window(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("v", now=100.0) is True
        assert limiter.allow("v", now=101.0) is True
        assert limiter.allow("v", now=102.0) is False
        assert limiter.allow("v", now=161.0) is True


class TestRuntimeConfigApplyGuard:
    """#13: a broken frontier key must not dead-letter every message."""

    async def test_decrypt_failure_falls_back_to_local(self) -> None:
        from desk.ai.engine import AIEngine

        engine = AIEngine.__new__(AIEngine)  # skip __init__ (PII model download)
        engine.local_provider = MagicMock(name="local")
        engine.frontier_provider = MagicMock(name="frontier")
        engine.model_router = SimpleNamespace(frontier_enabled=True)

        cfg = SimpleNamespace(
            id=uuid4(),
            updated_at=datetime.now(tz=UTC),
            local_model_name=None,
            local_model_endpoint=None,
            frontier_provider="openai",
            frontier_api_key_encrypted=b"not-valid-base64!!",
            frontier_model_name=None,
            confidence_threshold=None,
        )
        result = MagicMock()
        result.scalar_one_or_none.return_value = cfg
        session = AsyncMock()
        session.execute.return_value = result
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session

        with patch("desk.ai.engine.AsyncSessionLocal", return_value=session_cm):
            # Must not raise: previously the decrypt error escaped into
            # process_detailed and every message was dead-lettered forever.
            await engine._refresh_runtime_config()

        assert engine.frontier_provider is None  # _select_provider falls back to local
        assert engine.local_provider is not None
        # Stamp advanced so the broken config is not retried on every message.
        assert engine._applied_cfg_stamp == cfg.updated_at.isoformat()

        # Second call with unchanged config is a no-op (cached stamp).
        with patch("desk.ai.engine.AsyncSessionLocal", return_value=session_cm):
            await engine._refresh_runtime_config()
        assert engine.frontier_provider is None


class TestProcessorConsumerName:
    """#9: consumer name must be per-process for PEL attribution/recovery."""

    async def test_consumer_name_includes_pid(self) -> None:
        from desk.workers.message_processor import MessageProcessor

        bus = MagicMock()
        bus.subscribe = AsyncMock(side_effect=[[], asyncio.CancelledError()])
        processor = MessageProcessor(
            event_bus=bus,
            outbound_dispatcher=MagicMock(),
            ai_engine=MagicMock(),
        )
        await processor.run()
        kwargs = bus.subscribe.call_args_list[0].kwargs
        assert kwargs["consumer_name"] == f"processor-{os.getpid()}"
        assert kwargs["consumer_group"] == "ai-processors"


class TestRetentionSweepWiring:
    """#12: the retention helper must actually invoke the compliance engine."""

    async def test_sweep_calls_enforce_retention_policy(self) -> None:
        import desk.main as main_mod

        session_cm = AsyncMock()
        engine = MagicMock()
        engine.enforce_retention_policy = AsyncMock(
            return_value={"deleted_conversations": 3, "retention_days": 365}
        )
        with (
            patch.object(main_mod, "AsyncSessionLocal", return_value=session_cm),
            patch.object(main_mod, "ComplianceEngine", return_value=engine) as ctor,
        ):
            summary = await main_mod._retention_sweep()

        ctor.assert_called_once()
        engine.enforce_retention_policy.assert_awaited_once()
        assert summary["deleted_conversations"] == 3

    def test_retention_interval_setting_exists(self) -> None:
        from desk.config import Settings

        settings = Settings()
        assert settings.retention_scan_interval_seconds >= 60
