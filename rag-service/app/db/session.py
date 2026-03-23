from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings


def _strip_asyncpg_driver(database_url: str) -> str:
    return database_url.replace("+asyncpg", "")


def build_runtime_database_url(database_url: str, *, use_pgbouncer: bool) -> str:
    if not use_pgbouncer or "+asyncpg" not in database_url:
        return database_url

    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("prepared_statement_cache_size", "0")
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def build_migration_database_url(settings: Settings) -> str:
    database_url = settings.database_direct_url or settings.database_url
    return _strip_asyncpg_driver(database_url)


def build_engine_kwargs(settings: Settings) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if settings.database_use_pgbouncer:
        kwargs["poolclass"] = NullPool
    return kwargs


settings = get_settings()
engine = create_async_engine(
    build_runtime_database_url(
        settings.database_url,
        use_pgbouncer=settings.database_use_pgbouncer,
    ),
    **build_engine_kwargs(settings),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
