# Queue Slice Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real ARQ-backed async ingest for `pdf` and `web`, including worker execution and retry persistence.

**Architecture:** Keep API enqueue behavior thin, move actual async document processing into a shared ingestion processing path, and expose an ARQ worker entrypoint that updates job state in PostgreSQL. Retry handling stays in the worker path and writes back to `rag_ingestion_jobs`.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, Redis, ARQ, PostgreSQL, pytest

---

## Chunk 1: Queue Contract

### Task 1: Lock ARQ dispatch behavior with tests

**Files:**
- Create: `rag-service/tests/test_dispatch.py`
- Modify: `rag-service/app/services/dispatch.py`

- [ ] Write failing tests for enqueue payload and ARQ job name
- [ ] Run targeted tests and verify failure
- [ ] Implement ARQ-backed dispatcher minimally
- [ ] Re-run targeted tests and verify pass

## Chunk 2: Worker Processing

### Task 2: Lock shared async processing and worker behavior

**Files:**
- Create: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/workers/tasks/ingest.py`

- [ ] Write failing tests for async worker completing jobs and updating statuses
- [ ] Run targeted tests and verify failure
- [ ] Extract shared processing path and implement worker task
- [ ] Re-run targeted tests and verify pass

## Chunk 3: Retry Persistence

### Task 3: Lock retry and failure persistence

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/workers/tasks/ingest.py`

- [ ] Write failing tests for retry_count, error_message, and deferred retry behavior
- [ ] Run targeted tests and verify failure
- [ ] Implement retry persistence with exponential backoff
- [ ] Re-run targeted tests and verify pass

## Chunk 4: Runtime Wiring

### Task 4: Wire worker into local runtime

**Files:**
- Modify: `rag-service/docker-compose.yml`
- Modify: `rag-service/requirements.txt`
- Modify: `rag-service/app/main.py`

- [ ] Add runtime dependency and worker service
- [ ] Run focused tests
- [ ] Run full test suite
- [ ] Update checklist items that are now justified
