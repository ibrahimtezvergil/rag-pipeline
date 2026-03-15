# RAG Service P1 Foundation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the complete foundation for the RAG service: project skeleton, Docker Compose stack, PostgreSQL schema with Alembic, authentication middleware, and health endpoint with service status checks.

**Architecture:** FastAPI application with pydantic-settings config, SQLAlchemy 2.x async ORM models, and Alembic migrations. Auth via X-API-Key + X-Project-ID headers enforced in Starlette middleware. All services (PostgreSQL, Qdrant, Redis, Langfuse) run in Docker Compose. Local dev runs infra only via Docker; FastAPI runs directly with uvicorn.

**Tech Stack:** Python 3.11+, FastAPI 0.115, SQLAlchemy 2.x (asyncio), Alembic, pydantic-settings, asyncpg, httpx, redis[asyncio], pytest, pytest-asyncio, httpx

---

## Scope Note

This is **Plan 1 of 3** for P1 Core Infrastructure:
- **Plan 1 (this):** Foundation — project skeleton, Docker, DB schema, auth, health
- **Plan 2:** Ingestion Pipeline — loaders, chunker, Gemini Embedding 2, Qdrant, ARQ, `/ingest`
- **Plan 3:** Query Pipeline — hybrid search, Cohere rerank, `/query`, `/chat`, LangGraph

Spec: `rag_service_plan_v3.md` + `rag_service_checklist_v3.md`

---

## File Structure

```
rag-service/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, middleware mount
│   ├── config.py                # pydantic-settings Settings class
│   ├── deps.py                  # shared FastAPI dependencies (DB session)
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── auth.py              # X-API-Key + X-Project-ID enforcement
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py            # mounts all sub-routers
│   │   └── health.py            # GET /health — service status checks
│   ├── models/
│   │   ├── __init__.py
│   │   └── db.py                # SQLAlchemy ORM models (all 8 tables)
│   └── db/
│       ├── __init__.py
│       └── session.py           # async engine + AsyncSessionLocal factory
├── migrations/
│   ├── env.py                   # async Alembic env
│   ├── script.py.mako
│   └── versions/
│       └── 001_initial_schema.py
├── tests/
│   ├── conftest.py              # pytest fixtures: app client, valid headers
│   ├── test_health.py
│   └── test_auth.py
├── pytest.ini                   # asyncio_mode = auto
├── docker-compose.yml           # full stack; api/langfuse profile-gated
├── Dockerfile
├── .env.example
├── .env.test                    # test environment values
├── alembic.ini
└── requirements.txt
```

---

## Chunk 1: Project Bootstrap

### Task 1: Create directory structure and requirements

**Files:**
- Create: `rag-service/requirements.txt`
- Create: `rag-service/.env.example`
- Create: `rag-service/.env.test`
- Create: `rag-service/app/__init__.py`
- Create: `rag-service/app/config.py`

- [ ] **Step 1: Create all directories**

```bash
mkdir -p rag-service/app/middleware \
         rag-service/app/api \
         rag-service/app/models \
         rag-service/app/db \
         rag-service/tests \
         rag-service/migrations/versions \
         rag-service/workers/tasks
touch rag-service/app/__init__.py \
      rag-service/app/middleware/__init__.py \
      rag-service/app/api/__init__.py \
      rag-service/app/models/__init__.py \
      rag-service/app/db/__init__.py \
      rag-service/workers/__init__.py \
      rag-service/workers/tasks/__init__.py \
      rag-service/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic-settings==2.4.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.2
httpx==0.27.0
redis[asyncio]==5.0.8
python-dotenv==1.0.1

# test
pytest==8.3.2
pytest-asyncio==0.24.0
anyio[asyncio]==4.4.0
```

- [ ] **Step 3: Write .env.example**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=rag_chunks

# Redis
REDIS_URL=redis://localhost:6379

# Gemini
GEMINI_API_KEY=your_key_here
EMBED_MODEL=gemini-embedding-2-preview
EMBED_DIMENSION=768

# Auth — comma-separated valid API keys
API_KEYS=key1,key2

# Cohere
COHERE_API_KEY=your_key_here
```

- [ ] **Step 4: Write .env.test**

```bash
DATABASE_URL=postgresql+asyncpg://rag:rag@localhost:5432/ragdb_test
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=rag_chunks_test
REDIS_URL=redis://localhost:6379
GEMINI_API_KEY=test-key
EMBED_MODEL=gemini-embedding-2-preview
EMBED_DIMENSION=768
API_KEYS=test-key-1,test-key-2
COHERE_API_KEY=test-cohere-key
```

- [ ] **Step 5: Write app/config.py**

```python
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Allows pointing to a different .env file via ENV_FILE env var.
    # Tests set ENV_FILE=.env.test before importing the app.
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"), extra="ignore"
    )

    database_url: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_chunks"
    redis_url: str = "redis://localhost:6379"
    gemini_api_key: str
    embed_model: str = "gemini-embedding-2-preview"
    embed_dimension: int = 768
    api_keys: str  # comma-separated
    cohere_api_key: str = ""

    @property
    def api_keys_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


settings = Settings()
```

- [ ] **Step 6: Write .gitignore**

```gitignore
.env
.env.test
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
dist/
*.egg-info/
```

- [ ] **Step 7: Initialize git and commit**

```bash
cd rag-service
git init
git add .
git commit -m "feat: initialize project structure, config, and requirements"
```

---

### Task 2: Docker Compose setup

**Files:**
- Create: `rag-service/Dockerfile`
- Create: `rag-service/docker-compose.yml`

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
version: "3.9"

services:
  api:
    build: .
    profiles: ["api"]  # only starts when --profile api is given; never in dev
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      redis:
        condition: service_started

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: rag
      POSTGRES_DB: ragdb
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag -d ragdb"]
      interval: 5s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:v1.9.0
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  langfuse:
    image: langfuse/langfuse:2
    profiles: ["observability"]  # opt-in: docker compose --profile observability up
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://rag:rag@postgres:5432/langfuse
      NEXTAUTH_SECRET: changeme-in-prod
      NEXTAUTH_URL: http://localhost:3000
      SALT: changeme-in-prod
    depends_on:
      postgres:
        condition: service_healthy
      langfuse-init:
        condition: service_completed_successfully

  langfuse-init:
    image: postgres:16-alpine
    profiles: ["observability"]
    environment:
      PGPASSWORD: rag
    command: >
      psql -h postgres -U rag -tc
      "SELECT 1 FROM pg_database WHERE datname='langfuse'" |
      grep -q 1 || psql -h postgres -U rag -c "CREATE DATABASE langfuse;"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

- [ ] **Step 3: Note on docker-compose.dev.yml**

`docker-compose.dev.yml` is **not needed**. With the `profiles: ["api"]` pattern in `docker-compose.yml`, running `docker compose up -d` starts only unprovisioned services (postgres, qdrant, redis). The `api` container is excluded unless `--profile api` is explicitly passed. Local development command:

```bash
# Start infra only (api excluded — no profile flag)
docker compose up -d

# Full stack including API container:
docker compose --profile api up -d

# Include Langfuse observability:
docker compose --profile api --profile observability up -d
```

- [ ] **Step 4: Start infra and verify**

```bash
docker compose up -d
docker compose ps
```

Expected: postgres (healthy), qdrant (running), redis (running). `api` and `langfuse` are excluded (profile-gated).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Docker Compose stack with profile-gated api and langfuse"
```

---

## Chunk 2: Database Schema

### Task 3: SQLAlchemy models (all 8 tables)

**Files:**
- Create: `rag-service/app/db/session.py`
- Create: `rag-service/app/models/db.py`

- [ ] **Step 1: Write app/db/session.py**

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
```

- [ ] **Step 2: Write app/models/db.py**

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    UUID, BigInteger, Boolean, DateTime, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
)


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "rag_tenants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="tenant")


class Project(Base):
    __tablename__ = "rag_projects"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="projects")
    documents: Mapped[list["Document"]] = relationship(back_populates="project")


class Document(Base):
    __tablename__ = "rag_documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    project_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_projects.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_tenants.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(500))
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    version: Mapped[int] = mapped_column(Integer, default=1)
    previous_document_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_documents.id")
    )
    source_connector_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    embed_model: Mapped[str | None] = mapped_column(String(100))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    project: Mapped["Project"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document")
    jobs: Mapped[list["IngestionJob"]] = relationship(back_populates="document")


class Chunk(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_documents.id"), nullable=False
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_chunks.id")
    )
    qdrant_point_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    modality: Mapped[str] = mapped_column(String(20), default="text")
    token_count: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    section_title: Mapped[str | None] = mapped_column(String(500))
    acl: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    embed_model: Mapped[str | None] = mapped_column(String(100))
    embed_version: Mapped[str | None] = mapped_column(String(50))
    dimension: Mapped[int] = mapped_column(Integer, default=768)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")


class IngestionJob(Base):
    __tablename__ = "rag_ingestion_jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    document_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_documents.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    chunks_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    document: Mapped["Document"] = relationship(back_populates="jobs")


class ChunkDiffLog(Base):
    __tablename__ = "rag_chunk_diff_log"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    job_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("rag_ingestion_jobs.id"),
        nullable=False,
    )
    chunk_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_chunks.id")
    )
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class SyncCheckpoint(Base):
    __tablename__ = "rag_sync_checkpoints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    source_connector_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), nullable=False, unique=True
    )
    cursor_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class TenantSecret(Base):
    __tablename__ = "tenant_secrets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("rag_tenants.id"), nullable=False
    )
    key_type: Mapped[str] = mapped_column(String(50), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
```

- [ ] **Step 3: Commit**

```bash
git add app/models/db.py app/db/session.py
git commit -m "feat: add SQLAlchemy ORM models for all 8 tables"
```

---

### Task 4: Alembic async migrations

**Files:**
- Create: `rag-service/alembic.ini`
- Modify: `rag-service/migrations/env.py`
- Create: `rag-service/migrations/versions/001_initial_schema.py`

- [ ] **Step 1: Initialize Alembic and fix script_location**

```bash
cd rag-service
alembic init migrations
# alembic init defaults to script_location = alembic — update it:
sed -i '' 's/^script_location = alembic/script_location = migrations/' alembic.ini
```

Verify `alembic.ini` now has `script_location = migrations` (not `alembic`).

- [ ] **Step 2: Replace migrations/env.py with async version**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.models.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 3: Create test DB and run autogenerate**

```bash
docker compose exec postgres psql -U rag -c "CREATE DATABASE ragdb_test;"
alembic revision --autogenerate -m "initial_schema"
alembic upgrade head
```

- [ ] **Step 4: Verify all 8 tables exist**

```bash
docker compose exec postgres psql -U rag -d ragdb -c "\dt"
```

Expected output includes: `rag_tenants`, `rag_projects`, `rag_documents`, `rag_chunks`, `rag_ingestion_jobs`, `rag_chunk_diff_log`, `rag_sync_checkpoints`, `tenant_secrets`

- [ ] **Step 5: Commit**

```bash
git add alembic.ini migrations/
git commit -m "feat: add Alembic async migrations for initial schema"
```

---

## Chunk 3: Auth Middleware + Health Endpoint

### Task 5: Write failing auth tests first (TDD)

**Files:**
- Create: `rag-service/tests/conftest.py`
- Create: `rag-service/tests/test_auth.py`

- [ ] **Step 1: Write pytest.ini**

```ini
[pytest]
asyncio_mode = auto
```

This enables async fixtures and test functions without needing `@pytest.mark.anyio` on every item.

- [ ] **Step 2: Write tests/conftest.py**

```python
import os

# Must be set BEFORE any app import so pydantic-settings picks up .env.test
os.environ["ENV_FILE"] = ".env.test"

import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def valid_headers():
    return {"X-API-Key": "test-key-1", "X-Project-ID": "proj-abc"}
```

- [ ] **Step 3: Write tests/test_auth.py**

```python
# No @pytest.mark.anyio needed — pytest.ini sets asyncio_mode = auto.
# Adding anyio markers with asyncio_mode = auto causes an event loop split
# between the fixture (pytest-asyncio loop) and the test (anyio loop).


async def test_missing_api_key_returns_401(client):
    resp = await client.get("/health", headers={"X-Project-ID": "proj"})
    assert resp.status_code == 401


async def test_invalid_api_key_returns_401(client):
    resp = await client.get(
        "/health", headers={"X-API-Key": "wrong-key", "X-Project-ID": "proj"}
    )
    assert resp.status_code == 401


async def test_missing_project_id_returns_422(client):
    resp = await client.get("/health", headers={"X-API-Key": "test-key-1"})
    assert resp.status_code == 422


async def test_valid_headers_pass_through(client, valid_headers):
    resp = await client.get("/health", headers=valid_headers)
    assert resp.status_code == 200
```

- [ ] **Step 4: Run tests — verify they FAIL**

```bash
cd rag-service
pip install -r requirements.txt
pytest tests/test_auth.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `app.main` does not exist yet.

---

### Task 6: Implement auth middleware and FastAPI app

**Files:**
- Create: `rag-service/app/middleware/auth.py`
- Create: `rag-service/app/api/health.py`
- Create: `rag-service/app/api/router.py`
- Create: `rag-service/app/main.py`
- Create: `rag-service/app/deps.py`

- [ ] **Step 1: Write app/middleware/auth.py**

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

# Paths that bypass auth (OpenAPI docs)
_PUBLIC_PATHS = {"/docs", "/redoc", "/openapi.json"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key not in settings.api_keys_set:
            # IMPORTANT: must return JSONResponse, NOT raise HTTPException.
            # HTTPException raised inside BaseHTTPMiddleware.dispatch()
            # is caught by Starlette and converted to 500, not 401.
            return JSONResponse(
                {"detail": "Invalid or missing API key"}, status_code=401
            )

        project_id = request.headers.get("X-Project-ID")
        if not project_id:
            return JSONResponse(
                {"detail": "X-Project-ID header is required"}, status_code=422
            )

        request.state.project_id = project_id
        request.state.api_key = api_key
        return await call_next(request)
```

- [ ] **Step 2: Write app/deps.py**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 3: Write app/api/health.py**

```python
from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "embed_model": settings.embed_model,
    }
```

- [ ] **Step 4: Write app/api/router.py**

```python
from fastapi import APIRouter

from app.api.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
```

- [ ] **Step 5: Write app/main.py**

```python
from fastapi import FastAPI

from app.middleware.auth import AuthMiddleware
from app.api.router import api_router

app = FastAPI(title="RAG Service", version="0.1.0")
app.add_middleware(AuthMiddleware)
app.include_router(api_router)
```

- [ ] **Step 6: Run auth tests — verify they PASS**

```bash
pytest tests/test_auth.py -v
```

Expected: 4/4 PASS

- [ ] **Step 7: Commit**

```bash
git add app/middleware/ app/api/ app/main.py app/deps.py tests/
git commit -m "feat: add auth middleware, FastAPI app factory, and /health endpoint"
```

---

### Task 7: Write and pass health endpoint tests

**Files:**
- Create: `rag-service/tests/test_health.py`

- [ ] **Step 1: Write tests/test_health.py**

```python
# asyncio_mode = auto — no @pytest.mark.anyio needed on test functions.


async def test_health_returns_ok(client, valid_headers):
    resp = await client.get("/health", headers=valid_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "embed_model" in data


async def test_health_without_auth_returns_401(client):
    resp = await client.get("/health")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: 6/6 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_health.py
git commit -m "test: add health endpoint tests"
```

---

## Chunk 4: Extended Health Check (Service Status)

### Task 8: Health check with real service probes

**Files:**
- Modify: `rag-service/app/api/health.py`
- Modify: `rag-service/tests/test_health.py`

- [ ] **Step 1: Add failing test for service status**

Add to `tests/test_health.py`:

```python
async def test_health_includes_service_status(client, valid_headers):
    resp = await client.get("/health", headers=valid_headers)
    data = resp.json()
    assert "postgres" in data
    assert "qdrant" in data
    assert "redis" in data
    assert "embedder" in data
    assert data["status"] in ("ok", "degraded", "down")
```

- [ ] **Step 2: Run to verify it FAILS**

```bash
pytest tests/test_health.py::test_health_includes_service_status -v
```

Expected: FAIL — `"postgres"` not in response.

- [ ] **Step 3: Update app/api/health.py**

```python
import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.db.session import engine

router = APIRouter(tags=["health"])


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "down"


async def _check_qdrant() -> str:
    try:
        # Use GET / — returns 200 with version info on all Qdrant versions.
        # /healthz was introduced after v1.9.0 and does not exist in that release.
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.qdrant_url}/")
            return "ok" if r.status_code == 200 else "down"
    except Exception:
        return "down"


async def _check_redis() -> str:
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception:
        return "down"


@router.get("/health")
async def health():
    service_status = {
        "postgres": await _check_postgres(),
        "qdrant": await _check_qdrant(),
        "redis": await _check_redis(),
        "embedder": "ok",  # extended in Plan 2 when embedder client is added
    }
    overall = (
        "ok" if all(v == "ok" for v in service_status.values()) else "degraded"
    )
    return {
        "status": overall,
        "embed_model": settings.embed_model,
        **service_status,
    }
```

- [ ] **Step 4: Run all tests with infra running**

```bash
# Infra must be up (no -f flags needed; profiles handle service exclusion)
docker compose up -d

pytest tests/ -v
```

Expected: 7/7 PASS

- [ ] **Step 5: Manual smoke test**

```bash
uvicorn app.main:app --reload &
curl -s -H "X-API-Key: test-key-1" -H "X-Project-ID: proj-abc" \
     http://localhost:8000/health | python3 -m json.tool
```

Expected response:
```json
{
  "status": "ok",
  "embed_model": "gemini-embedding-2-preview",
  "postgres": "ok",
  "qdrant": "ok",
  "redis": "ok",
  "embedder": "ok"
}
```

- [ ] **Step 6: Commit**

```bash
git add app/api/health.py tests/test_health.py
git commit -m "feat: extend /health with postgres, qdrant, redis service probes"
```

---

## Execution Checklist (Quick Reference)

```bash
# 1. Start infra (api and langfuse excluded — profile-gated)
docker compose up -d

# 2. Install deps
pip install -r requirements.txt

# 3. Run migrations
alembic upgrade head

# 4. Run all tests (infra must be running)
pytest tests/ -v

# 5. Start API locally
uvicorn app.main:app --reload

# 6. Smoke test
curl -H "X-API-Key: test-key-1" -H "X-Project-ID: proj-abc" \
     http://localhost:8000/health

# Optional: full stack with API container
# docker compose --profile api up -d

# Optional: with Langfuse observability
# docker compose --profile api --profile observability up -d
```

---

**Plan complete. Ready to execute?**

Next plan: `2026-03-15-p2-ingestion-pipeline.md` — loaders, chunker, Gemini Embedding 2, Qdrant upsert, ARQ queue, `/ingest` endpoint.
