# Budget Enforcement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `latency_budget_ms` ve `token_budget` alanlarını query/chat akışında çalışan enforcement haline getirmek.

**Architecture:** `QueryService` retrieval sonrası kalan süreyi hesaplayacak ve generate öncesi hard latency gate uygulayacak. Token budget tarafında source ve context blokları yaklaşık token hesabıyla kademeli küçültülecek; prompt builder aynı kalacak, sadece kırpılmış input alacak.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, existing query/chat services, observability events

---

## Chunk 1: Tests First

### Task 1: Latency budget davranışı

**Files:**
- Modify: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - latency budget hit olduğunda `generate_text()` çağrılmıyor
  - latency budget hit olduğunda `_fallback_answer()` sonucu dönüyor

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k latency_budget
```

- [ ] **Step 3: Write minimal implementation**
Implement remaining-budget check in `QueryService.answer_question`.

- [ ] **Step 4: Run test to verify it passes**
Run same command and confirm green.

### Task 2: Token budget trimming davranışı

**Files:**
- Modify: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Write the failing test**
Add tests for:
  - düşük token budget ile prompt'a daha az source/context gidiyor
  - budget yoksa mevcut prompt kapsamı korunuyor

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k token_budget
```

- [ ] **Step 3: Write minimal implementation**
Implement approximate token trimming helpers in `QueryService`.

- [ ] **Step 4: Run test to verify it passes**
Run same command and confirm green.

## Chunk 2: Implementation

### Task 3: Query service budget enforcement

**Files:**
- Modify: `rag-service/app/services/query.py`

- [ ] **Step 1: Add latency budget helpers**
Resolve config safely, compute remaining ms, define minimum generate safety window.

- [ ] **Step 2: Add token budget helpers**
Approximate tokens with `len(text)//4`, trim source count, parent context and snippet lengths.

- [ ] **Step 3: Integrate into answer flow**
Apply token trimming before prompt build; apply latency gate before `generate_text`.

- [ ] **Step 4: Preserve backward compatibility**
No config means existing behavior.

### Task 4: Observability metadata

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Emit budget metadata**
Include `latency_budget_ms`, `latency_budget_hit`, `remaining_budget_ms`, `token_budget`, `token_trimmed`, `prompt_estimated_tokens`.

- [ ] **Step 2: Add/adjust tests**
Verify event payload includes budget metadata.

## Chunk 3: Verification

### Task 5: Focused suite

**Files:**
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Run focused tests**

```bash
cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py tests/test_api_endpoints.py
```

- [ ] **Step 2: Fix any regression**

- [ ] **Step 3: Re-run until green**

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

- [ ] **Step 2: Confirm green and report exact pass count**

