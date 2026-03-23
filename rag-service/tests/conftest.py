import os
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


os.environ["ENV_FILE"] = ".env.test"

from app.main import create_app
from app.models.db import (
    Base,
    RagChunk,
    RagChunkDiffLog,
    RagDocument,
    RagIngestionJob,
    RagProject,
    RagSchedule,
    RagSyncCheckpoint,
    RagTenant,
    TenantSecret,
)
from app.services.circuit_breaker import reset_circuit_breakers


@pytest.fixture(autouse=True)
def reset_circuit_breaker_state():
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
def valid_headers() -> dict[str, str]:
    return {
        "X-API-Key": "test-key-1",
        "X-Project-ID": str(uuid4()),
    }


@pytest.fixture
async def integration_session():
    database_url = os.getenv(
        "INTEGRATION_DATABASE_URL",
        "postgresql+asyncpg://rag:rag@127.0.0.1:55432/ragdb",
    )
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        for model in (
            RagSchedule,
            RagChunkDiffLog,
            RagSyncCheckpoint,
            TenantSecret,
            RagChunk,
            RagIngestionJob,
            RagDocument,
            RagProject,
            RagTenant,
        ):
            await session.execute(delete(model))
        await session.commit()
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
async def seeded_project(integration_session: AsyncSession):
    tenant = RagTenant(name="Test Tenant", api_key_hash="hashed-key")
    integration_session.add(tenant)
    await integration_session.flush()

    project = RagProject(
        id=uuid4(),
        tenant_id=tenant.id,
        name="Test Project",
        config={},
    )
    integration_session.add(project)
    await integration_session.commit()
    project_row = await integration_session.get(RagProject, project.id)
    assert project_row is not None

    return {
        "tenant_id": tenant.id,
        "project_id": project.id,
    }
