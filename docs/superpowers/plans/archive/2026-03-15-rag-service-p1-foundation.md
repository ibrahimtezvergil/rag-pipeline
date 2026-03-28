# RAG Service P1 Foundation Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first working foundation of `rag-service` with app scaffolding, infrastructure config, database schema, authentication middleware, and a health endpoint.

**Architecture:** The service will be a standalone FastAPI app under `rag-service/`. Configuration lives in `app/config.py`, infra clients in `app/services/`, database concerns in `app/db/` and `app/models/`, and HTTP concerns in `app/api/` plus middleware. Tests will verify auth and health behavior before implementation is added.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy asyncio, Alembic, PostgreSQL, Redis, Qdrant, pytest, httpx

---

## Chunk 1: Project Bootstrap

### Task 1: Create the service skeleton and config files

**Files:**
- Create: `rag-service/requirements.txt`
- Create: `rag-service/.env.example`
- Create: `rag-service/.env.test`
- Create: `rag-service/.gitignore`
- Create: `rag-service/app/__init__.py`
- Create: `rag-service/app/config.py`
- Create: `rag-service/app/main.py`

- [ ] Create the `rag-service/` directory structure for `app/`, `tests/`, `migrations/`, and `workers/`
- [ ] Add dependency pins for FastAPI, SQLAlchemy async, Alembic, Redis, httpx, and pytest
- [ ] Add example environment files for local and test execution
- [ ] Implement `Settings` in `app/config.py`
- [ ] Add a minimal app factory in `app/main.py`

### Task 2: Add container and local run scaffolding

**Files:**
- Create: `rag-service/docker-compose.yml`
- Create: `rag-service/Dockerfile`
- Create: `rag-service/alembic.ini`
- Create: `rag-service/pytest.ini`

- [ ] Add Docker Compose services for API, PostgreSQL, Redis, Qdrant, and Langfuse
- [ ] Add a Python 3.11 Dockerfile for the API image
- [ ] Add Alembic and pytest base config

## Chunk 2: Database Foundation

### Task 3: Add async DB session and ORM models

**Files:**
- Create: `rag-service/app/db/__init__.py`
- Create: `rag-service/app/db/session.py`
- Create: `rag-service/app/models/__init__.py`
- Create: `rag-service/app/models/db.py`

- [ ] Define shared SQLAlchemy metadata and async engine/session factory
- [ ] Implement the P1 tables from the v3 checklist as SQLAlchemy models
- [ ] Expose metadata for Alembic autogeneration and app startup

### Task 4: Add Alembic migration scaffolding

**Files:**
- Create: `rag-service/migrations/env.py`
- Create: `rag-service/migrations/script.py.mako`
- Create: `rag-service/migrations/versions/001_initial_schema.py`

- [ ] Configure Alembic for async SQLAlchemy metadata
- [ ] Write an initial migration that creates the schema required for P1

## Chunk 3: HTTP Surface

### Task 5: Write failing tests for auth and health

**Files:**
- Create: `rag-service/tests/__init__.py`
- Create: `rag-service/tests/conftest.py`
- Create: `rag-service/tests/test_auth.py`
- Create: `rag-service/tests/test_health.py`

- [ ] Write tests that require auth headers on protected endpoints
- [ ] Write tests that reject invalid API keys
- [ ] Write tests that validate `/health` service status output using dependency overrides
- [ ] Run pytest and confirm the new tests fail for the expected reasons

### Task 6: Implement middleware, router, and health endpoint

**Files:**
- Create: `rag-service/app/deps.py`
- Create: `rag-service/app/api/__init__.py`
- Create: `rag-service/app/api/router.py`
- Create: `rag-service/app/api/health.py`
- Create: `rag-service/app/middleware/__init__.py`
- Create: `rag-service/app/middleware/auth.py`
- Create: `rag-service/app/services/__init__.py`
- Create: `rag-service/app/services/health.py`

- [ ] Add auth middleware enforcing `X-API-Key` and `X-Project-ID`
- [ ] Add a protected sample endpoint to exercise middleware in tests
- [ ] Add reusable service check functions for PostgreSQL, Redis, and Qdrant
- [ ] Implement `/health` with aggregated status reporting
- [ ] Run pytest until all auth and health tests pass

## Chunk 4: Verification

### Task 7: Verify the foundation end to end

**Files:**
- Verify: `rag-service/...`

- [ ] Run the test suite from `rag-service/`
- [ ] Review generated files for missing imports or config mismatches
- [ ] Summarize any remaining gaps relative to full P1 scope
