import json

import pytest

from app.services import query_cache as query_cache_module


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex

    async def sadd(self, key: str, *values: str):
        members = self.sets.setdefault(key, set())
        members.update(values)

    async def smembers(self, key: str):
        return self.sets.get(key, set())

    async def delete(self, *keys: str):
        for key in keys:
            self.deleted.append(key)
            self.values.pop(key, None)
            self.sets.pop(key, None)

    async def expire(self, key: str, seconds: int):
        self.expirations[key] = seconds


def test_query_cache_build_key_is_deterministic_and_scoped():
    service = query_cache_module.RedisQueryCache(redis=FakeRedis(), ttl_seconds=3600)

    first = service.build_key(
        question="Revenue in Q1?",
        tenant_id="tenant-1",
        project_id="project-1",
        scope_id="customer-1",
        tags=["crm"],
    )
    second = service.build_key(
        question="Revenue in Q1?",
        tenant_id="tenant-1",
        project_id="project-1",
        scope_id="customer-1",
        tags=["crm"],
    )
    different = service.build_key(
        question="Revenue in Q1?",
        tenant_id="tenant-2",
        project_id="project-1",
        scope_id="customer-1",
        tags=["crm"],
    )

    assert first == second
    assert first != different
    assert first.startswith("query_cache:item:")


@pytest.mark.asyncio
async def test_query_cache_get_set_and_project_index():
    redis = FakeRedis()
    service = query_cache_module.RedisQueryCache(redis=redis, ttl_seconds=3600)
    cache_key = service.build_key(question="Q", tenant_id="t", project_id="p")
    payload = {"answer": "cached", "sources": []}

    await service.set(cache_key=cache_key, project_id="p", value=payload)
    result = await service.get(cache_key)

    assert result == payload
    assert redis.expirations[cache_key] == 3600
    assert redis.expirations["query_cache:index:p"] == 3600
    assert cache_key in redis.sets["query_cache:index:p"]


@pytest.mark.asyncio
async def test_query_cache_invalidates_project_keys():
    redis = FakeRedis()
    service = query_cache_module.RedisQueryCache(redis=redis, ttl_seconds=3600)
    first = service.build_key(question="Q1", tenant_id="t", project_id="p")
    second = service.build_key(question="Q2", tenant_id="t", project_id="p")
    await service.set(cache_key=first, project_id="p", value={"answer": "one"})
    await service.set(cache_key=second, project_id="p", value={"answer": "two"})

    await service.invalidate_project("p")

    assert await service.get(first) is None
    assert await service.get(second) is None
    assert "query_cache:index:p" in redis.deleted


@pytest.mark.asyncio
async def test_query_cache_fails_open_when_redis_errors():
    class BrokenRedis:
        async def get(self, key: str):
            raise RuntimeError("redis down")

    service = query_cache_module.RedisQueryCache(redis=BrokenRedis(), ttl_seconds=3600)

    assert await service.get("query_cache:item:test") is None
