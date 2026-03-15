# Structured Ingest Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic `structured` ingest flow that accepts `records[]`, formats them into text with `SummaryFormatter`, and runs them through the existing chunk/embed/upsert pipeline with tenant-safe scope metadata.

**Architecture:** Extend the ingest schema with a new `structured` source type and inline payload fields. Add a dedicated structured loader that turns generic records into formatted text plus metadata, then reuse the existing ingestion pipeline unchanged after load. Persist optional scope metadata on the document and propagate it into vector payloads.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, pytest, existing ARQ/Qdrant ingestion services

---

## Chunk 1: Request Contract

### Task 1: Extend ingest request schema for structured payloads

**Files:**
- Modify: `rag-service/app/schemas/ingest.py`
- Test: `rag-service/tests/test_ingest.py`

- [ ] **Step 1: Write the failing API tests**
  Add tests for `POST /ingest` accepting:
  - `source_type="structured"`
  - `title`
  - `records`
  - optional `scope_type`, `scope_id`, `entity_type`, `tags`

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py`
  Expected: FAIL because `structured` and payload fields are not supported.

- [ ] **Step 3: Write minimal schema implementation**
  Update `IngestRequest` to support:
  - `source_type="structured"`
  - `title: str | None`
  - `records: list[dict] | None`
  - `scope_type: str | None`
  - `scope_id: str | None`
  - `entity_type: str | None`
  - `tags: list[str] | None`
  Add validator rules so:
  - `structured` requires `records`
  - non-structured sources reject `records`
  - existing pdf/web/db rules stay intact

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py`
  Expected: PASS

## Chunk 2: Structured Loader

### Task 2: Add structured loader and SummaryFormatter integration

**Files:**
- Modify: `rag-service/app/services/loaders.py`
- Test: `rag-service/tests/test_loaders.py`

- [ ] **Step 1: Write the failing loader tests**
  Add tests proving `load_source("structured", ...)`:
  - formats `records[]` via `SummaryFormatter`
  - preserves `title`
  - stores `record_count`
  - stores `scope_type`, `scope_id`, `entity_type`, `tags`

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py`
  Expected: FAIL because structured loader path does not exist.

- [ ] **Step 3: Write minimal loader implementation**
  Add `load_structured_source(...)` and dispatch from `load_source(...)`.
  Return:
  - `content`
  - `metadata`
  - `chunk_count`

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py`
  Expected: PASS

## Chunk 3: Ingestion Service Wiring

### Task 3: Persist structured metadata and process it through the existing pipeline

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Test: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing service tests**
  Add sync ingestion tests proving structured payloads:
  - create a document
  - store scope metadata
  - call the structured loader path
  - reach chunk/embed/index flow

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv313/bin/python -m pytest -q tests/test_ingestion_service.py`
  Expected: FAIL because structured metadata is not persisted/loaded.

- [ ] **Step 3: Write minimal service implementation**
  Persist structured payload metadata on document creation and load it in `_process_document_job`.
  Ensure `_derive_title()` and `_source_ref()` handle structured payloads.

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv313/bin/python -m pytest -q tests/test_ingestion_service.py`
  Expected: PASS

## Chunk 4: Regression Verification

### Task 4: Run focused and full verification

**Files:**
- Test: `rag-service/tests/test_ingest.py`
- Test: `rag-service/tests/test_loaders.py`
- Test: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Run focused verification**
  Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py tests/test_loaders.py tests/test_ingestion_service.py`
  Expected: PASS

- [ ] **Step 2: Run full verification**
  Run: `.venv313/bin/python -m pytest -q`
  Expected: PASS

- [ ] **Step 3: Update checklist if warranted**
  If implementation is complete, update relevant checklist wording or notes without overstating scope.
