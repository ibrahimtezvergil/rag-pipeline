# RAG Evaluation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API ile tetiklenen, async worker üzerinden çalışan ve sonuçları DB'ye yazan bir RAG evaluation pipeline kurmak.

**Architecture:** Yeni evaluation run/sample tabloları ve bunları yöneten `EvaluationService` eklenecek. `POST /evaluations` run oluşturup worker job enqueue edecek; worker her sample için mevcut query pipeline'ı çalıştıracak, heuristic metrikleri hesaplayıp run/sample satırlarını güncelleyecek.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, ARQ, pytest

---

## Chunk 1: Tests First

### Task 1: API ve veri kontratı

**Files:**
- Modify: `rag-service/tests/test_api_endpoints.py`
- Modify: `rag-service/tests/test_models_or_repositories.py` (gerekirse yeni test dosyası)

- [ ] **Step 1: Write the failing test**
Add tests for:
  - `POST /evaluations` request kabulü
  - created run response shape
  - `GET /evaluations/{run_id}` status response

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py -k evaluation
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

### Task 2: Worker evaluation akışı

**Files:**
- Modify: `rag-service/tests/test_worker_schedules.py` or create `rag-service/tests/test_worker_evaluations.py`
- Create/Modify: `rag-service/tests/test_evaluations.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - worker sample'ları işler
  - sample score row yazar
  - run aggregate skorları günceller
  - sample failure run'ı bozmaz

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_evaluations.py tests/test_worker_evaluations.py
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: Implementation

### Task 3: DB modeli ve migration

**Files:**
- Modify: `rag-service/app/models/db.py`
- Create: `rag-service/migrations/versions/005_add_rag_evaluations.py`

- [ ] **Step 1: Add `rag_evaluation_runs` model**

- [ ] **Step 2: Add `rag_evaluation_samples` model**

- [ ] **Step 3: Add Alembic migration**

### Task 4: Schema, repository ve service

**Files:**
- Create: `rag-service/app/schemas/evaluations.py`
- Create: `rag-service/app/repositories/evaluations.py`
- Create: `rag-service/app/services/evaluations.py`

- [ ] **Step 1: Add request/response schema**

- [ ] **Step 2: Add repository helpers**

- [ ] **Step 3: Add heuristic metric helpers**

- [ ] **Step 4: Add run creation + processing flow**

### Task 5: API ve worker entegrasyonu

**Files:**
- Create: `rag-service/app/api/evaluations.py`
- Modify: `rag-service/app/api/router.py`
- Create: `rag-service/workers/tasks/evaluations.py`
- Modify: `rag-service/workers/tasks/ingest.py` or worker settings file as needed

- [ ] **Step 1: Add `POST /evaluations`**

- [ ] **Step 2: Add `GET /evaluations/{run_id}`**

- [ ] **Step 3: Add ARQ worker function**

- [ ] **Step 4: Register worker function**

## Chunk 3: Verification

### Task 6: Focused verification

**Files:**
- Test: `rag-service/tests/test_api_endpoints.py`
- Test: `rag-service/tests/test_evaluations.py`
- Test: `rag-service/tests/test_worker_evaluations.py`

- [ ] **Step 1: Run focused suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_evaluations.py tests/test_worker_evaluations.py
```

- [ ] **Step 2: Fix regressions**

### Task 7: Full verification

**Files:**
- Test: `rag-service/tests/test_api_endpoints.py`
- Test: `rag-service/tests/test_audio_metadata.py`
- Test: `rag-service/tests/test_callbacks.py`
- Test: `rag-service/tests/test_chunking.py`
- Test: `rag-service/tests/test_deployment_config.py`
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
- Test: `rag-service/tests/test_observability.py`
- Test: `rag-service/tests/test_query_cache.py`
- Test: `rag-service/tests/test_query_expansion.py`
- Test: `rag-service/tests/test_rate_limit.py`
- Test: `rag-service/tests/test_schedules.py`
- Test: `rag-service/tests/test_tracing.py`
- Test: `rag-service/tests/test_worker_schedules.py`
- Test: `rag-service/tests/test_evaluations.py`
- Test: `rag-service/tests/test_worker_evaluations.py`

- [ ] **Step 1: Run full suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_audio_metadata.py tests/test_callbacks.py tests/test_chunking.py tests/test_deployment_config.py tests/test_embedder.py tests/test_ingest.py tests/test_ingestion_service.py tests/test_llm_service.py tests/test_query_service.py tests/test_reranker.py tests/test_sparse_encoder.py tests/test_vector_store.py tests/test_worker_ingest.py tests/test_circuit_breaker.py tests/test_db_session.py tests/test_observability.py tests/test_query_cache.py tests/test_query_expansion.py tests/test_rate_limit.py tests/test_schedules.py tests/test_tracing.py tests/test_worker_schedules.py tests/test_evaluations.py tests/test_worker_evaluations.py
```

- [ ] **Step 2: Confirm green and record exact pass count**
