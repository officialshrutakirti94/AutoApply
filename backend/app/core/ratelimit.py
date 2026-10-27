"""A small in-process rate limiter.

Deliberately not Redis: v1 runs a single backend instance, and the endpoints that
need protection (sign-in, pairing, uploads) are cheap to count in memory. If the
API is ever scaled horizontally this must move to Redis or the platform edge,
because each instance would otherwise keep its own counters.

Used as a dependency or called directly:

    await check_rate_limit(request, bucket="auth", limit=10, window_seconds=60)
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import RateLimited


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, float]:
        now = time.monotonic()
        cutoff = now - window_seconds
        async with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(bucket[0] - cutoff, 0.0)
                return False, retry_after
            bucket.append(now)
            return True, 0.0

    async def reset(self) -> None:
        async with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def client_key(request: Request, bucket: str) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not ip and request.client:
        ip = request.client.host or ""
    return f"{bucket}:{ip or 'unknown'}"


async def check_rate_limit(
    request: Request, *, bucket: str, limit: int, window_seconds: int = 60
) -> None:
    allowed, retry_after = await limiter.hit(client_key(request, bucket), limit, window_seconds)
    if not allowed:
        raise RateLimited(
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
