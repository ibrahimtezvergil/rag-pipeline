from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.session import build_migration_database_url
from app.models.db import Base


settings = get_settings()
target_metadata = Base.metadata


def _get_config():
    config = context.config
    config.set_main_option("sqlalchemy.url", build_migration_database_url(settings))
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    return config


def run_migrations_offline() -> None:
    config = _get_config()
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config = _get_config()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if getattr(context, "config", None) is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
