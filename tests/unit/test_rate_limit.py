"""
ODW.ai Desk — Unit Tests for the Web-chat Rate Limiter (V1.4 F-4, W1)

A per-visitor sliding-window limiter: within the per-minute budget calls are
allowed; once the budget is exhausted further calls are rejected until the
window slides. Deterministic via an injected ``now``.
"""

from unittest.mock import MagicMock, patch

import desk.channels.rate_limit as rate_limit
from desk.channels.rate_limit import SlidingWindowRateLimiter, get_webchat_rate_limiter


class TestSlidingWindowRateLimiter:
    def test_within_limit_is_allowed(self):
        limiter = SlidingWindowRateLimiter(max_requests=3)
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is True
        assert limiter.allow("v1", now=2.0) is True

    def test_over_limit_is_rejected(self):
        limiter = SlidingWindowRateLimiter(max_requests=2)
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is True
        # Budget (2/min) exhausted -> rejected
        assert limiter.allow("v1", now=2.0) is False
        assert limiter.allow("v1", now=3.0) is False

    def test_window_slides_and_allows_again(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is True
        assert limiter.allow("v1", now=2.0) is False
        # After the window passes, the old events expire and a new one is allowed.
        assert limiter.allow("v1", now=61.0) is True

    def test_keys_are_isolated(self):
        limiter = SlidingWindowRateLimiter(max_requests=1)
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is False
        # A different visitor has its own budget.
        assert limiter.allow("v2", now=1.0) is True

    def test_remaining_reflects_budget(self):
        limiter = SlidingWindowRateLimiter(max_requests=3)
        assert limiter.remaining("v1", now=0.0) == 3
        limiter.allow("v1", now=0.0)
        assert limiter.remaining("v1", now=0.0) == 2

    def test_reset_clears_state(self):
        limiter = SlidingWindowRateLimiter(max_requests=1)
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is False
        limiter.reset("v1")
        assert limiter.allow("v1", now=2.0) is True

    def test_max_requests_floor_of_one(self):
        limiter = SlidingWindowRateLimiter(max_requests=0)
        assert limiter.max_requests == 1
        assert limiter.allow("v1", now=0.0) is True
        assert limiter.allow("v1", now=1.0) is False


class TestWebchatLimiterFactory:
    def test_uses_configured_budget(self):
        settings = MagicMock()
        settings.webchat_rate_limit_per_min = 7

        rate_limit._webchat_limiter = None
        try:
            with patch("desk.channels.rate_limit.get_settings", return_value=settings):
                limiter = get_webchat_rate_limiter()
            assert limiter.max_requests == 7
            # Cached singleton: a second call returns the same instance.
            assert get_webchat_rate_limiter() is limiter
        finally:
            rate_limit._webchat_limiter = None
