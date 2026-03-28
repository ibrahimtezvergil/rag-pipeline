# Chunk Diff And Reuse Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Previous version child chunk hash'lerini kullanarak unchanged text chunk'larda embed skip + vector reuse yapmak ve diff log yazmak.

**Architecture:** Ingestion service previous child snapshot + Qdrant vector fetch yapar, `_build_chunk_rows` text path'inde unchanged hash'lerde vector reuse eder. Job sonunda `rag_chunk_diff_log` satirlari `new/modified/unchanged/deleted` olarak yazilir.

**Tech Stack:** SQLAlchemy repository, Qdrant HTTP API, ingestion service, pytest

---

## Chunk 1: Storage support

### Task 1: Qdrant vector fetch ve diff log repository desteği

**Files:**
- Modify: `rag-service/app/services/vector_store.py`
- Modify: `rag-service/app/repositories/ingestion.py`
- Modify: `rag-service/tests/test_vector_store.py`

- [ ] Step 1: failing tests yaz (`fetch_dense_vectors`, `create_chunk_diff_logs`)
- [ ] Step 2: fail'i gor
- [ ] Step 3: helper'lari implement et
- [ ] Step 4: green al

## Chunk 2: Ingestion orchestration

### Task 2: unchanged chunk reuse

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: unchanged hash -> embed skip/vector reuse failing testini yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: previous child map + vector fetch + build flow'u ekle
- [ ] Step 4: green al

### Task 3: diff log write

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: `new/modified/unchanged/deleted` diff log failing testini yaz
- [ ] Step 2: fail'i gor
- [ ] Step 3: diff entry production path'ini ekle
- [ ] Step 4: green al

## Chunk 3: Verification and checklist

### Task 4: Verify touched surface

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: focused suite calistir
- [ ] Step 2: `Chunk-level hash karşılaştırma` ve `Diff log yazımı` maddelerini kapat
- [ ] Step 3: DB integration limits varsa not et
