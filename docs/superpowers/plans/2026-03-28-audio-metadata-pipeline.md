# Audio Metadata Pipeline Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audio ingest akışına opsiyonel transcript ve segment metadata eklemek, mevcut embedding akışını kırmadan semantik audio chunk üretmek.

**Architecture:** `audio_metadata.py` best-effort metadata extraction sağlayacak; `IngestionService` audio document metadata ve clip chunk content üretiminde bunu kullanacak. Provider yoksa veya hata verirse mevcut clip summary fallback korunacak.

**Tech Stack:** FastAPI service layer, existing audio loader/embed flow, pytest, SQLAlchemy async, existing ingestion repository

---

## Chunk 1: Tests First

### Task 1: Audio metadata success path

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - metadata başarılıysa document metadata içine transcript/segments yazılır
  - chunk content transcript segmentinden üretilir

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k audio_metadata
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

### Task 2: Fallback davranışı

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - metadata unavailable ise clip summary fallback
  - metadata exception ingest'i fail etmez

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k audio_metadata_fallback
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: Implementation

### Task 3: Audio metadata service

**Files:**
- Create: `rag-service/app/services/audio_metadata.py`
- Test: `rag-service/tests/test_audio_metadata.py`

- [ ] **Step 1: Add service contract**
Implement best-effort `extract_audio_metadata(...)`.

- [ ] **Step 2: Add provider/config fallback**
No dependency or disabled config should return `status=unavailable`.

- [ ] **Step 3: Add tests**
Unit tests for unavailable/error/ok payload normalization.

### Task 4: Ingestion integration

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/app/config.py`

- [ ] **Step 1: Wire metadata extraction into audio path**

- [ ] **Step 2: Persist document audio metadata**

- [ ] **Step 3: Build chunk content from transcript segments when available**

- [ ] **Step 4: Preserve existing fallback summary path**

## Chunk 3: Verification

### Task 5: Focused verification

**Files:**
- Test: `rag-service/tests/test_audio_metadata.py`
- Test: `rag-service/tests/test_worker_ingest.py`
- Test: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Run focused suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_audio_metadata.py tests/test_worker_ingest.py tests/test_ingestion_service.py
```

- [ ] **Step 2: Fix regressions**

### Task 6: Full verification

**Files:**
- Test: `rag-service/tests/test_api_endpoints.py`
- Test: `rag-service/tests/test_chunking.py`
- Test: `rag-service/tests/test_embedder.py`
- Test: `rag-service/tests/test_ingestion_service.py`
- Test: `rag-service/tests/test_llm_service.py`
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_reranker.py`
- Test: `rag-service/tests/test_sparse_encoder.py`
- Test: `rag-service/tests/test_vector_store.py`
- Test: `rag-service/tests/test_worker_ingest.py`
- Test: `rag-service/tests/test_circuit_breaker.py`
- Test: `rag-service/tests/test_db_session.py`
- Test: `rag-service/tests/test_deployment_config.py`
- Test: `rag-service/tests/test_observability.py`
- Test: `rag-service/tests/test_query_cache.py`
- Test: `rag-service/tests/test_query_expansion.py`
- Test: `rag-service/tests/test_rate_limit.py`
- Test: `rag-service/tests/test_schedules.py`
- Test: `rag-service/tests/test_tracing.py`
- Test: `rag-service/tests/test_worker_schedules.py`

- [ ] **Step 1: Run full suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_chunking.py tests/test_embedder.py tests/test_ingestion_service.py tests/test_llm_service.py tests/test_query_service.py tests/test_reranker.py tests/test_sparse_encoder.py tests/test_vector_store.py tests/test_worker_ingest.py tests/test_circuit_breaker.py tests/test_db_session.py tests/test_deployment_config.py tests/test_observability.py tests/test_query_cache.py tests/test_query_expansion.py tests/test_rate_limit.py tests/test_schedules.py tests/test_tracing.py tests/test_worker_schedules.py
```

- [ ] **Step 2: Confirm green and record exact pass count**

