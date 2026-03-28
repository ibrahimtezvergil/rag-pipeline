# Ingestion Webhook Callback Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Async ingest job tamamlandığında veya final failure durumunda HMAC-imzalı callback göndermek.

**Architecture:** `IngestRequest` içine opsiyonel `callback_url` eklenecek, async dispatch payload bunu worker'a taşıyacak. Worker sonunda yeni `callbacks.py` servisi callback body ve `X-RAG-Signature` üreterek best-effort POST atacak; hata olursa ingest sonucu değişmeyecek.

**Tech Stack:** FastAPI schemas, ARQ worker, httpx, hashlib/hmac, pytest

---

## Chunk 1: Tests First

### Task 1: Request and dispatch contract

**Files:**
- Modify: `rag-service/tests/test_ingest.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - `IngestRequest` accepts `callback_url`
  - async ingest enqueue payload carries `callback_url`

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_ingest.py tests/test_ingestion_service.py -k callback
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

### Task 2: Worker callback behavior

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - completed async ingest triggers callback
  - final failed ingest triggers callback
  - callback failure does not break ingest result

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k callback
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: Implementation

### Task 3: Callback service

**Files:**
- Create: `rag-service/app/services/callbacks.py`
- Create: `rag-service/tests/test_callbacks.py`
- Modify: `rag-service/app/config.py`

- [ ] **Step 1: Add env config**
Add `ingest_callback_secret`.

- [ ] **Step 2: Add signature helper**
HMAC-SHA256 over raw JSON body.

- [ ] **Step 3: Add POST sender**
Best-effort `httpx.AsyncClient` with timeout.

- [ ] **Step 4: Add unit tests**
Verify payload and signature behavior.

### Task 4: Ingestion and worker integration

**Files:**
- Modify: `rag-service/app/schemas/ingest.py`
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/workers/tasks/ingest.py`

- [ ] **Step 1: Add `callback_url` to request schema**

- [ ] **Step 2: Persist/dispatch callback_url**

- [ ] **Step 3: Invoke callback on worker completion and final failure**

- [ ] **Step 4: Keep fail-open behavior**

## Chunk 3: Verification

### Task 5: Focused verification

**Files:**
- Test: `rag-service/tests/test_callbacks.py`
- Test: `rag-service/tests/test_ingest.py`
- Test: `rag-service/tests/test_ingestion_service.py`
- Test: `rag-service/tests/test_worker_ingest.py`

- [ ] **Step 1: Run focused suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_callbacks.py tests/test_ingest.py tests/test_ingestion_service.py tests/test_worker_ingest.py
```

- [ ] **Step 2: Fix regressions**

### Task 6: Full verification

**Files:**
- Test: `rag-service/tests/test_api_endpoints.py`
- Test: `rag-service/tests/test_audio_metadata.py`
- Test: `rag-service/tests/test_chunking.py`
- Test: `rag-service/tests/test_embedder.py`
- Test: `rag-service/tests/test_ingest.py`
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
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_audio_metadata.py tests/test_chunking.py tests/test_embedder.py tests/test_ingest.py tests/test_ingestion_service.py tests/test_llm_service.py tests/test_query_service.py tests/test_reranker.py tests/test_sparse_encoder.py tests/test_vector_store.py tests/test_worker_ingest.py tests/test_circuit_breaker.py tests/test_db_session.py tests/test_deployment_config.py tests/test_observability.py tests/test_query_cache.py tests/test_query_expansion.py tests/test_rate_limit.py tests/test_schedules.py tests/test_tracing.py tests/test_worker_schedules.py
```

- [ ] **Step 2: Confirm green and report exact pass count**

