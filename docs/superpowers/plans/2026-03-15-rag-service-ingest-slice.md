# RAG Service Ingest Slice Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first ingest vertical slice for `pdf` and `web` sources with request acceptance, job creation, status lookup, and sync/async modes.

**Architecture:** HTTP handlers stay thin and delegate to an ingestion service. The service persists `rag_documents` and `rag_ingestion_jobs` through a repository layer and can either finish immediately (`sync`) or leave the job pending (`async`). Worker code is scaffolded separately so later ARQ integration does not force API rewrites.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy asyncio, pytest

---

## Chunk 1: HTTP Contract

### Task 1: Add failing endpoint tests

**Files:**
- Create: `rag-service/tests/test_ingest.py`
- Modify: `rag-service/tests/conftest.py`

- [ ] Write tests for `POST /ingest` with `pdf` and `web`
- [ ] Write tests for `sync` and `async` mode behavior
- [ ] Write tests for `GET /ingest/{id}` status lookup
- [ ] Run tests and confirm failure before implementation

## Chunk 2: App Implementation

### Task 2: Add ingest schemas and API routes

**Files:**
- Create: `rag-service/app/schemas/__init__.py`
- Create: `rag-service/app/schemas/ingest.py`
- Create: `rag-service/app/api/ingest.py`
- Modify: `rag-service/app/api/router.py`
- Modify: `rag-service/app/main.py`

- [ ] Define request and response schemas
- [ ] Add route handlers for create and status lookup
- [ ] Wire the ingest service into app state

### Task 3: Add repository and service layer

**Files:**
- Create: `rag-service/app/repositories/__init__.py`
- Create: `rag-service/app/repositories/ingestion.py`
- Create: `rag-service/app/services/ingestion.py`

- [ ] Persist documents and jobs
- [ ] Implement thin sync and async mode handling
- [ ] Add lookup by ingestion job id

## Chunk 3: Worker Scaffold and Verification

### Task 4: Add worker scaffold

**Files:**
- Create: `rag-service/workers/tasks/ingest.py`

- [ ] Add placeholder task entrypoint for future background processing

### Task 5: Verify and update tracking docs

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Run the full test suite
- [ ] Mark newly completed ingest checklist items only if verified
