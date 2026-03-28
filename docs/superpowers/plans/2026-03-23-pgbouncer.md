# PgBouncer Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Runtime PostgreSQL bağlantılarını PgBouncer transaction pooling üzerinden geçirmek ve app/runtime/migration ayarlarını buna uyumlu hale getirmek.

**Architecture:** `docker-compose` içine ayrı bir PgBouncer servisi eklenecek. Runtime app `DATABASE_URL` ile PgBouncer'a bağlanacak, session engine PgBouncer modunda `NullPool` ve asyncpg prepared statement cache kapatma kurallarıyla açılacak, Alembic ise `DATABASE_DIRECT_URL` üzerinden doğrudan PostgreSQL kullanacak.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, Alembic, Docker Compose, PgBouncer, pytest

---

## Chunk 1: Runtime Session Wiring

### Task 1: PgBouncer-aware DB helpers

**Files:**
- Modify: `rag-service/app/config.py`
- Modify: `rag-service/app/db/session.py`
- Modify: `rag-service/migrations/env.py`
- Test: `rag-service/tests/test_db_session.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_runtime_database_url_disables_prepared_statement_cache():
    ...

def test_build_engine_kwargs_uses_nullpool_for_pgbouncer():
    ...

def test_selects_direct_database_url_for_migrations():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_db_session.py`
Expected: FAIL because helper functions/settings do not exist yet

- [ ] **Step 3: Write minimal implementation**

Add new settings (`database_direct_url`, `database_use_pgbouncer`) and pure helper functions in `app/db/session.py` plus migration URL resolver in `migrations/env.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_db_session.py`
Expected: PASS

## Chunk 2: Docker Compose Wiring

### Task 2: Add PgBouncer service and runtime env config

**Files:**
- Modify: `rag-service/docker-compose.yml`
- Modify: `rag-service/.env.example`
- Create: `rag-service/docker/pgbouncer/Dockerfile`
- Create: `rag-service/docker/pgbouncer/entrypoint.sh`
- Create: `rag-service/docker/pgbouncer/pgbouncer.ini.tmpl`
- Test: `rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compose_routes_runtime_services_via_pgbouncer():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py`
Expected: FAIL because compose lacks `pgbouncer`

- [ ] **Step 3: Write minimal implementation**

Add PgBouncer service, route `api`/`worker` DB URL to `pgbouncer:6432`, expose direct URL separately, and generate PgBouncer config from env at container start.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py`
Expected: PASS

## Chunk 3: Verification And Checklist

### Task 3: Focused regression verification

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] **Step 1: Run focused regression suite**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_db_session.py tests/test_deployment_config.py tests/test_health.py tests/test_api_endpoints.py`
Expected: PASS

- [ ] **Step 2: Update checklist**

Mark `PgBouncer` item complete with short `Ref:` and `Akış:` note.
