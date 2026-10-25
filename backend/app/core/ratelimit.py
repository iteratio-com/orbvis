"""Simple in-memory rate limiter (no external dependencies)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from app.core.config import settings


class RateLimiter:
    """Sliding-window rate limiter keyed by arbitrary string (e.g. client IP).

    Thread-safe; suitable for single-process deployments.
    """

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune_key(self, key: str, cutoff: float) -> deque[float] | None:
        """Drop timestamps older than cutoff; evict the key entirely when empty.

        Must be called under self._lock. Returns the still-populated deque, or
        None if the key has been evicted — preventing the _calls dict from
        growing unbounded for bursty one-off sources (NAT-masked clients,
        scanners, etc.).
        """
        q = self._calls.get(key)
        if q is None:
            return None
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            del self._calls[key]
            return None
        return q

    def is_blocked(self, key: str) -> bool:
        """Return True if the key has exceeded the limit (check only, does not record)."""
        now = time.monotonic()
        with self._lock:
            q = self._prune_key(key, now - self._window)
            return q is not None and len(q) >= self._max

    def record(self, key: str) -> None:
        """Record one failed attempt for key."""
        now = time.monotonic()
        with self._lock:
            self._prune_key(key, now - self._window)
            self._calls[key].append(now)

    def retry_after(self, key: str) -> float:
        """Seconds until the oldest recorded attempt falls outside the window."""
        now = time.monotonic()
        with self._lock:
            q = self._prune_key(key, now - self._window)
            if q is None:
                return 0.0
            return max(0.0, q[0] + self._window - now)


class ConcurrencyLimiter:
    """Caps how many resources are held at once, per key and in total.

    Where RateLimiter caps the *rate* of new acquisitions, this caps how many
    are *held simultaneously*. Thread-safe; suitable for single-process
    deployments.
    """

    def __init__(self, max_per_key: int, max_total: int) -> None:
        self._max_per_key = max_per_key
        self._max_total = max_total
        self._counts: dict[str, int] = {}
        self._total = 0
        self._lock = Lock()

    def try_acquire(self, key: str) -> bool:
        """Reserve one slot for key; return False (reserving nothing) when full."""
        with self._lock:
            held = self._counts.get(key, 0)
            if self._total >= self._max_total or held >= self._max_per_key:
                return False
            self._counts[key] = held + 1
            self._total += 1
            return True

    def release(self, key: str) -> None:
        """Give back one slot previously acquired for key (no-op at zero)."""
        with self._lock:
            held = self._counts.get(key, 0)
            if held <= 0:
                return
            if held == 1:
                del self._counts[key]
            else:
                self._counts[key] = held - 1
            self._total -= 1


# 5 failed login attempts per 15 minutes per IP
login_limiter = RateLimiter(max_calls=5, window_seconds=15 * 60)

# 30 stream handshakes per minute per authenticated user — covers typical
# reconnect storms (tab restore, laptop wake) but blocks scripted connection
# floods. Keyed by user, not IP: behind the OMD double Apache every request
# arrives from the loopback proxy hop, so an IP key would share one budget
# across all users.
ws_connect_limiter = RateLimiter(max_calls=30, window_seconds=60)

sse_stream_limiter = ConcurrencyLimiter(
    max_per_key=settings.sse_max_streams_per_user, max_total=settings.sse_max_streams_total
)

# Worldmap tile proxy: a pan/zoom burst legitimately pulls a few hundred tiles
# per minute; the cap only stops scripted cache-fill/bandwidth abuse.
tile_fetch_limiter = RateLimiter(max_calls=600, window_seconds=60)
