from __future__ import annotations

import asyncio

import httpx
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db.session import engine


ServiceStatus = dict[str, str]


async def check_postgres() -> ServiceStatus:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return {"status": "down", "detail": str(exc)}
    return {"status": "up"}


async def check_redis() -> ServiceStatus:
    client = redis_from_url(get_settings().redis_url)
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - network failure branch
        return {"status": "down", "detail": str(exc)}
    finally:
        await client.aclose()
    return {"status": "up"}


async def check_qdrant() -> ServiceStatus:
    try:
        async with httpx.AsyncClient(base_url=get_settings().qdrant_url, timeout=5.0) as client:
            response = await client.get("/collections")
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failure branch
        return {"status": "down", "detail": str(exc)}
    return {"status": "up"}


async def check_embedder() -> ServiceStatus:
    settings = get_settings()
    if not settings.gemini_api_key.strip():
        return {"status": "down", "detail": "Missing Gemini API key"}

    return {"status": "up", "model": settings.embed_model}


async def collect_health_status() -> dict[str, ServiceStatus]:
    postgres, redis, qdrant, embedder = await asyncio.gather(
        check_postgres(),
        check_redis(),
        check_qdrant(),
        check_embedder(),
    )
    return {
        "postgres": postgres,
        "redis": redis,
        "qdrant": qdrant,
        "embedder": embedder,
    }
