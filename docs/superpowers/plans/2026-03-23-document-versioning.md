# Document Versioning Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ayni source icin yeni ingestion geldiginde version zinciri olusturmak ve eski aktif versiyonu supersede etmek.

**Architecture:** Ingestion create path'i once latest active document'i bulur ve yeni row'a `version/previous_document_id` yazar. Basarili indexing sonrasi previous version archive+vector delete ile supersede edilir; failure halinde old version yerinde kalir.

**Tech Stack:** SQLAlchemy repository, ingestion service, existing vector store, pytest

---

## Chunk 1: Repository support

### Task 1: Version lookup ve create contract

**Files:**
- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: latest document lookup ve versioned create icin failing tests yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: repository API'lerini ekle
- [ ] Step 4: green al

## Chunk 2: Ingestion orchestration

### Task 2: create_ingestion_job version assignment

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: second ingest version increment testini yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: version/previous_document_id assignment ekle
- [ ] Step 4: green al

### Task 3: successful indexing supersede flow

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: successful supersede + vector delete testi yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: previous version archive/supersede akisini ekle
- [ ] Step 4: green al

## Chunk 3: Verification and checklist

### Task 4: Verify touched area

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: focused ingestion suite calistir
- [ ] Step 2: `Document versioning` maddesini kapat
- [ ] Step 3: DB-dependent tests ortam blokluysa not et
