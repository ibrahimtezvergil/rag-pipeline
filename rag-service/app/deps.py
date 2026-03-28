from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.config import get_settings
from app.services.rate_limit import RedisSlidingWindowRateLimiter


@dataclass(slots=True)
class RequestContext:
    application_id: str
    api_key: str


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        application_id=request.state.application_id,
        api_key=request.state.api_key,
    )


def get_rate_limiter(request: Request) -> RedisSlidingWindowRateLimiter:
    service = getattr(request.app.state, "rate_limiter", None)
    if service is not None:
        return service
    limiter = RedisSlidingWindowRateLimiter()
    request.app.state.rate_limiter = limiter
    return limiter


def require_rate_limit(route_name: str, limit_value: int):
    async def dependency(request: Request) -> None:
        limiter = get_rate_limiter(request)
        result = await limiter.check(
            application_id=request.state.application_id,
            route_name=route_name,
            limit=limit_value,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(result.retry_after_seconds or 1)},
            )

    return dependency


query_rate_limit = require_rate_limit(
    "query",
    get_settings().rate_limit_query_per_minute,
)
chat_rate_limit = require_rate_limit(
    "chat",
    get_settings().rate_limit_chat_per_minute,
)
ingest_rate_limit = require_rate_limit(
    "ingest",
    get_settings().rate_limit_ingest_per_minute,
)
ingest_batch_rate_limit = require_rate_limit(
    "ingest_batch",
    get_settings().rate_limit_ingest_batch_per_minute,
)
