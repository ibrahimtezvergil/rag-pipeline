import pytest

from app.services import rate_limit as rate_limit_module


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, list[tuple[str, float]]] = {}
        self.expirations: dict[str, int] = {}

    async def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> None:
        items = self.values.get(key, [])
        self.values[key] = [
            (member, score) for member, score in items if not (minimum <= score <= maximum)
        ]

    async def zcard(self, key: str) -> int:
        return len(self.values.get(key, []))

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        items = self.values.setdefault(key, [])
        for member, score in mapping.items():
            items.append((member, score))

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    async def zrange(
        self,
        key: str,
        start: int,
        end: int,
        *,
        withscores: bool = False,
    ):
        items = sorted(self.values.get(key, []), key=lambda item: item[1])
        selected = items[start : end + 1]
        if withscores:
            return selected
        return [member for member, _score in selected]


@pytest.mark.asyncio
async def test_rate_limiter_allows_requests_under_limit():
    limiter = rate_limit_module.RedisSlidingWindowRateLimiter(redis=FakeRedis())

    result = await limiter.check(
        application_id="project-1",
        route_name="query",
        limit=2,
        window_seconds=60,
        now=100.0,
    )

    assert result.allowed is True
    assert result.retry_after_seconds is None


@pytest.mark.asyncio
async def test_rate_limiter_rejects_requests_over_limit_and_returns_retry_after():
    limiter = rate_limit_module.RedisSlidingWindowRateLimiter(redis=FakeRedis())

    await limiter.check(
        application_id="project-1",
        route_name="query",
        limit=1,
        window_seconds=60,
        now=100.0,
    )
    result = await limiter.check(
        application_id="project-1",
        route_name="query",
        limit=1,
        window_seconds=60,
        now=110.0,
    )

    assert result.allowed is False
    assert result.retry_after_seconds == 50


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_when_redis_errors():
    class BrokenRedis:
        async def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> None:
            raise RuntimeError("redis down")

    limiter = rate_limit_module.RedisSlidingWindowRateLimiter(redis=BrokenRedis())

    result = await limiter.check(
        application_id="project-1",
        route_name="query",
        limit=1,
        window_seconds=60,
        now=100.0,
    )

    assert result.allowed is True
    assert result.retry_after_seconds is None
