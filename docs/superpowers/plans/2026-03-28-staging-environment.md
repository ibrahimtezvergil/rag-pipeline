# Staging Environment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repo içinde production-benzeri ama izole bir staging compose/env/runbook katmanı oluşturmak.

**Architecture:** Yeni `docker-compose.staging.yml` aynı servis setini staging port/volume/DB isimleriyle ayağa kaldıracak. `.env.staging.example` staging env kontratını gösterecek, operasyon runbook'u migration ve smoke test adımlarını dokümante edecek.

**Tech Stack:** Docker Compose, env files, markdown runbook, pytest file-content tests

---

## Chunk 1: Tests First

### Task 1: Staging compose/env beklentileri

**Files:**
- Modify: `rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - `docker-compose.staging.yml` exists
  - staging compose uses distinct ports/volumes
  - `.env.staging.example` exists and contains required keys

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py -k staging
```

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

### Task 2: Runbook beklentileri

**Files:**
- Modify: `rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Write the failing test**
Add test for staging runbook presence and required commands.

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Write minimal implementation**

- [ ] **Step 4: Run test to verify it passes**

## Chunk 2: Implementation

### Task 3: Staging compose and env

**Files:**
- Create: `rag-service/docker-compose.staging.yml`
- Create: `rag-service/.env.staging.example`

- [ ] **Step 1: Add isolated staging service graph**

- [ ] **Step 2: Use distinct ports and volume names**

- [ ] **Step 3: Keep service parity with main compose**

### Task 4: Staging runbook

**Files:**
- Create: `docs/operations/rag-service-staging-runbook.md`

- [ ] **Step 1: Document bring-up steps**

- [ ] **Step 2: Document migration step**

- [ ] **Step 3: Document smoke test sequence**

## Chunk 3: Verification

### Task 5: Focused verification

**Files:**
- Test: `rag-service/tests/test_deployment_config.py`

- [ ] **Step 1: Run focused suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_deployment_config.py
```

- [ ] **Step 2: Fix regressions**

### Task 6: Full verification

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

- [ ] **Step 1: Run full suite**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py tests/test_audio_metadata.py tests/test_callbacks.py tests/test_chunking.py tests/test_deployment_config.py tests/test_embedder.py tests/test_ingest.py tests/test_ingestion_service.py tests/test_llm_service.py tests/test_query_service.py tests/test_reranker.py tests/test_sparse_encoder.py tests/test_vector_store.py tests/test_worker_ingest.py tests/test_circuit_breaker.py tests/test_db_session.py tests/test_observability.py tests/test_query_cache.py tests/test_query_expansion.py tests/test_rate_limit.py tests/test_schedules.py tests/test_tracing.py tests/test_worker_schedules.py
```

- [ ] **Step 2: Confirm green and record exact pass count**

