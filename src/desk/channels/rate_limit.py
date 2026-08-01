"""
ODW.ai Desk — Web-chat Rate Limiter (V1.4 F-4)

A small in-memory sliding-window rate limiter keyed by visitor id, used to
protect the web-chat WebSocket endpoint from abuse. The per-minute budget is
configurable via ``webchat_rate_limit_per_min`` (default 30 — deliberately
lenient so normal visitors are never affected).

State is process-local and best-effort: it is not shared across workers, which
is acceptable for abuse mitigation at this edge layer.
"""

import time
from collections import defaultdict, deque

import structlog

from desk.config import get_settings

logger = structlog.get_logger()

# Length of the sliding window. The configurable budget is "per minute".
WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """
    Per-key sliding-window rate limiter.

    ``allow(key)`` returns True and records the event when the number of events
    within the trailing ``window_seconds`` is below ``max_requests``; otherwise
    it returns False. Rejected calls are NOT recorded, so a burst above the limit
    does not extend the lockout beyond the natural window.

    A monotonic clock is used by default; tests may inject an explicit ``now``
    for deterministic assertions.
    """

    def __init__(self, max_requests: int, window_seconds: float = WINDOW_SECONDS) -> None:
        self.max_requests = max(1, max_requests)
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        """Drop events that have fallen out of the trailing window."""
        window = self._events[key]
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()
        return window

    def allow(self, key: str, now: float | None = None) -> bool:
        """Return True (and record the event) when within the limit, else False."""
        timestamp = now if now is not None else time.monotonic()
        window = self._prune(key, timestamp)
        if len(window) >= self.max_requests:
            return False
        window.append(timestamp)
        return True

    def remaining(self, key: str, now: float | None = None) -> int:
        """Requests still allowed for ``key`` within the current window."""
        timestamp = now if now is not None else time.monotonic()
        window = self._prune(key, timestamp)
        return max(0, self.max_requests - len(window))

    def reset(self, key: str | None = None) -> None:
        """Forget recorded events for one key, or for all keys when key is None."""
        if key is None:
            self._events.clear()
        else:
            self._events.pop(key, None)


# Process-wide limiter for the web-chat endpoint, created lazily so the budget
# is read from settings on first use. Tests typically construct their own
# instance (or patch ``get_webchat_rate_limiter``) with an explicit budget.
_webchat_limiter: SlidingWindowRateLimiter | None = None


def get_webchat_rate_limiter() -> SlidingWindowRateLimiter:
    """Return the shared web-chat rate limiter (lenient default budget)."""
    global _webchat_limiter
    if _webchat_limiter is None:
        _webchat_limiter = SlidingWindowRateLimiter(
            max_requests=get_settings().webchat_rate_limit_per_min
        )
    return _webchat_limiter
