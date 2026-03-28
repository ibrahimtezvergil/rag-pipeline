from __future__ import annotations

from urllib.parse import urlparse
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings


class IngestionDispatcher(Protocol):
    async def enqueue(self, payload: dict[str, str]) -> None: ...


class EvaluationDispatcher(Protocol):
    async def enqueue(self, payload: dict[str, str]) -> None: ...


class NullIngestionDispatcher:
    async def enqueue(self, payload: dict[str, str]) -> None:
        return None


class NullEvaluationDispatcher:
    async def enqueue(self, payload: dict[str, str]) -> None:
        return None


class ArqIngestionDispatcher:
    def __init__(self, redis_url: str | None = None, *, pool: ArqRedis | None = None) -> None:
        self.redis_url = redis_url
        self.pool = pool

    async def enqueue(self, payload: dict[str, str]) -> None:
        pool = self.pool or await create_pool(_redis_settings_from_url(self.redis_url or get_settings().redis_url))
        await pool.enqueue_job(
            "run_ingest_job",
            payload,
            _job_id=payload["ingestion_job_id"],
        )


class ArqEvaluationDispatcher:
    def __init__(self, redis_url: str | None = None, *, pool: ArqRedis | None = None) -> None:
        self.redis_url = redis_url
        self.pool = pool

    async def enqueue(self, payload: dict[str, str]) -> None:
        pool = self.pool or await create_pool(_redis_settings_from_url(self.redis_url or get_settings().redis_url))
        await pool.enqueue_job(
            "run_evaluation_job",
            payload,
            _job_id=payload["run_id"],
        )


def create_default_dispatcher() -> IngestionDispatcher:
    settings = get_settings()
    return ArqIngestionDispatcher(settings.redis_url)


def create_default_evaluation_dispatcher() -> EvaluationDispatcher:
    settings = get_settings()
    return ArqEvaluationDispatcher(settings.redis_url)


def _redis_settings_from_url(redis_url: str) -> RedisSettings:
    parsed = urlparse(redis_url)
    database = int((parsed.path or "/0").lstrip("/") or "0")
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=database,
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )
