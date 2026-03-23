# Sync Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basarili connector ingestion sonunda `rag_sync_checkpoints` row'unu upsert etmek.

**Architecture:** Ingest payload connector metadata tasir; document row bu metadata'yi saklar; ingestion success sonunda repository checkpoint row'unu create/update eder.

**Tech Stack:** FastAPI schema, SQLAlchemy repository, ingestion service, pytest

---

## Chunk 1: Schema and repository

### Task 1: Connector metadata and checkpoint upsert

**Files:**
- Modify: `rag-service/app/schemas/ingest.py`
- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: failing tests yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: schema/repository support ekle
- [ ] Step 4: green al

## Chunk 2: Ingestion integration

### Task 2: Successful ingest checkpoint update

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: failing integration/unit test yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: success path upsert ekle
- [ ] Step 4: green al

## Chunk 3: Verification

### Task 3: Verify touched surface

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: focused suite calistir
- [ ] Step 2: checkpoint maddesini kapat
