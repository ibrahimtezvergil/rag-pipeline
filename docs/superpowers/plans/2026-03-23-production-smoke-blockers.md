# Production Smoke Blockers Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current deploy and smoke-test blockers so the stack can build, start, ingest a PDF, answer a query, and still enforce rate limits.

**Architecture:** Keep the existing service boundaries, but align infra contracts and failure handling. The core changes are narrow: dependency resolution, compose topology, Alembic graph merge, Qdrant contract unification, and sync ingest failure finalization.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Qdrant, Redis, Docker Compose, pytest, httpx

---

## Chunk 1: Deployment Blockers

### Task 1: Add failing deployment tests

**Files:**
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_deployment_config.py`
- Test: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Write failing tests for dependency, PgBouncer, and Langfuse topology**
- [ ] **Step 2: Run `pytest -q tests/test_deployment_config.py` and confirm failures**
- [ ] **Step 3: Update `requirements.txt`, `docker/pgbouncer/Dockerfile`, `docker/pgbouncer/entrypoint.sh`, and `docker-compose.yml` minimally**
- [ ] **Step 4: Re-run `pytest -q tests/test_deployment_config.py` and confirm pass**

### Task 2: Fix Alembic multiple-head state

**Files:**
- Create: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/migrations/versions/004_merge_heads.py`
- Test: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Add a failing test that asserts a single Alembic head**
- [ ] **Step 2: Run the targeted test and confirm it fails**
- [ ] **Step 3: Add the merge revision with no-op upgrade/downgrade**
- [ ] **Step 4: Re-run the targeted test and confirm it passes**

## Chunk 2: Qdrant Contract

### Task 3: Lock collection schema and idempotency with tests

**Files:**
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_vector_store.py`
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_api_endpoints.py`
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/collections.py`
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/vector_store.py`

- [ ] **Step 1: Write failing tests for named-vector collection creation, `ensure_collection()` idempotency, and Qdrant query path payload**
- [ ] **Step 2: Run `pytest -q tests/test_vector_store.py tests/test_api_endpoints.py -k 'collection or qdrant'` and confirm failures**
- [ ] **Step 3: Implement the minimal contract fix in `collections.py` and `vector_store.py`**
- [ ] **Step 4: Re-run the targeted tests and confirm pass**

## Chunk 3: Sync Ingest Failure Finalization

### Task 4: Make sync ingest fail cleanly

**Files:**
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/tests/test_ingestion_service.py`
- Modify: `/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/ingestion.py`

- [ ] **Step 1: Add a failing test where sync ingest raises inside `_process_document_job()` and asserts job/document are finalized as `failed`**
- [ ] **Step 2: Run `pytest -q tests/test_ingestion_service.py -k sync` and confirm failure**
- [ ] **Step 3: Implement minimal exception handling in sync ingestion path**
- [ ] **Step 4: Re-run the targeted test and confirm pass**

## Chunk 4: Verification

### Task 5: Run focused regression suite

**Files:**
- Verify only

- [ ] **Step 1: Run focused pytest suite**
Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py tests/test_vector_store.py tests/test_api_endpoints.py tests/test_ingestion_service.py
```
- [ ] **Step 2: Confirm zero failures**

### Task 6: Re-run live smoke checks

**Files:**
- Verify only

- [ ] **Step 1: Run `docker-compose up -d`**
- [ ] **Step 2: Run `docker-compose ps` and confirm core services are up**
- [ ] **Step 3: Run live `/health`**
- [ ] **Step 4: Run sync PDF `/ingest` and confirm `indexed`**
- [ ] **Step 5: Run live `/query` and confirm sources**
- [ ] **Step 6: Run rate-limit smoke and confirm `429 + Retry-After`**
