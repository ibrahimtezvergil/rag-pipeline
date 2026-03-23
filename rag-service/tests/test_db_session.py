from sqlalchemy.pool import NullPool

from app.db import session
from app.config import Settings


def test_build_runtime_database_url_disables_prepared_statement_cache_for_pgbouncer():
    runtime_url = session.build_runtime_database_url(
        "postgresql+asyncpg://rag:rag@pgbouncer:6432/ragdb?sslmode=disable",
        use_pgbouncer=True,
    )

    assert "prepared_statement_cache_size=0" in runtime_url
    assert "sslmode=disable" in runtime_url


def test_build_runtime_database_url_preserves_existing_cache_setting():
    runtime_url = session.build_runtime_database_url(
        "postgresql+asyncpg://rag:rag@pgbouncer:6432/ragdb?prepared_statement_cache_size=7",
        use_pgbouncer=True,
    )

    assert runtime_url.count("prepared_statement_cache_size=") == 1
    assert "prepared_statement_cache_size=7" in runtime_url


def test_build_engine_kwargs_uses_nullpool_for_pgbouncer():
    settings = Settings(
        database_url="postgresql+asyncpg://rag:rag@pgbouncer:6432/ragdb",
        database_use_pgbouncer=True,
        gemini_api_key="test",
        api_keys="test-key",
    )

    kwargs = session.build_engine_kwargs(settings)

    assert kwargs["future"] is True
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["poolclass"] is NullPool


def test_build_migration_database_url_prefers_direct_database_url():
    settings = Settings(
        database_url="postgresql+asyncpg://rag:rag@pgbouncer:6432/ragdb",
        database_direct_url="postgresql+asyncpg://rag:rag@postgres:5432/ragdb",
        gemini_api_key="test",
        api_keys="test-key",
    )

    assert session.build_migration_database_url(settings) == "postgresql://rag:rag@postgres:5432/ragdb"
