# RAG Service Loaders Slice Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real `web` and `pdf` sync ingestion behavior that fetches source content, derives basic metadata, and updates document/job state.

**Architecture:** Keep loaders separate from ingestion orchestration. The ingestion service will call a source loader service only for `sync` mode; loader output will be reduced to a single extracted text blob plus metadata for now. `async` mode remains acceptance-only until ARQ is added.

**Tech Stack:** FastAPI, SQLAlchemy asyncio, httpx, pypdf, pytest

---

## Chunk 1: Contract

### Task 1: Add failing tests for sync loader behavior

**Files:**
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Add a failing test for `web` sync ingestion storing fetched metadata
- [ ] Add a failing test for `pdf` sync ingestion storing parsed metadata
- [ ] Verify the new tests fail before implementation

## Chunk 2: Implementation

### Task 2: Add loader services

**Files:**
- Create: `rag-service/app/services/loaders.py`
- Modify: `rag-service/requirements.txt`

- [ ] Add a web loader using `httpx`
- [ ] Add a PDF loader using `pypdf`
- [ ] Return normalized loader results with content and metadata

### Task 3: Connect loaders to ingestion orchestration

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/app/models/db.py`

- [ ] For `sync`, set document/job to running first, then finalize to indexed/completed
- [ ] Persist extracted metadata on the document row
- [ ] Store a minimal `chunk_count` for the first slice

## Chunk 3: Verification

### Task 4: Run tests

**Files:**
- Verify: `rag-service/...`

- [ ] Run targeted loader tests
- [ ] Run full suite
