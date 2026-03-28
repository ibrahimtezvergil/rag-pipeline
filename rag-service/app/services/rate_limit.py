from __future__ import annotations

from dataclasses import dataclass
from time import time
from uuid import uuid4

from redis.asyncio import Redis

from app.config import get_settings


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int | None = None


class RedisSlidingWindowRateLimiter:
    def __init__(self, redis: Redis | None = None):
        self.redis = redis or Redis.from_url(get_settings().redis_url, decode_responses=True)

    async def check(
        self,
        *,
        application_id: str,
        route_name: str,
        limit: int,
        window_seconds: int = 60,
        now: float | None = None,
    ) -> RateLimitResult:
        current = now if now is not None else time()
        key = f"rate_limit:{application_id}:{route_name}"
        window_start = current - window_seconds
        try:
            await self.redis.zremrangebyscore(key, 0, window_start)
            current_count = await self.redis.zcard(key)
            if current_count >= limit:
                oldest = await self.redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(1, int(window_seconds - (current - float(oldest[0][1]))))
                else:
                    retry_after = window_seconds
                return RateLimitResult(allowed=False, retry_after_seconds=retry_after)
            await self.redis.zadd(key, {str(uuid4()): current})
            await self.redis.expire(key, window_seconds)
            return RateLimitResult(allowed=True, retry_after_seconds=None)
        except Exception:
            return RateLimitResult(allowed=True, retry_after_seconds=None)
