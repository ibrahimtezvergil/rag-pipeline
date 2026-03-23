from __future__ import annotations

import hashlib
import json
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings


class RedisQueryCache:
    def __init__(self, redis: Redis | None = None, ttl_seconds: int | None = None) -> None:
        settings = get_settings()
        self.redis = redis or Redis.from_url(settings.redis_url, decode_responses=True)
        self.ttl_seconds = ttl_seconds or settings.query_cache_ttl_seconds

    def build_key(self, **payload: Any) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"query_cache:item:{digest}"

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        try:
            raw = await self.redis.get(cache_key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            return None

    async def set(self, *, cache_key: str, project_id: str, value: dict[str, Any]) -> None:
        index_key = self._index_key(project_id)
        try:
            await self.redis.set(cache_key, json.dumps(value, sort_keys=True), ex=self.ttl_seconds)
            await self.redis.sadd(index_key, cache_key)
            await self.redis.expire(index_key, self.ttl_seconds)
        except Exception:
            return

    async def invalidate_project(self, project_id: str) -> None:
        index_key = self._index_key(project_id)
        try:
            members = list(await self.redis.smembers(index_key))
            if members:
                await self.redis.delete(*members)
            await self.redis.delete(index_key)
        except Exception:
            return

    def _index_key(self, project_id: str) -> str:
        return f"query_cache:index:{project_id}"
