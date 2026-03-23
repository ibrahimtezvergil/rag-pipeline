# Circuit Breaker Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready process-local circuit breaker for Qdrant, Gemini embed, Gemini LLM, and Cohere rerank so repeated upstream failures fail fast and existing fallbacks stay intact.

**Architecture:** Add a small in-process breaker service with per-service state and integrate it at the provider boundary of each outbound dependency. Keep query behavior resilient by falling back on rerank skip or `_fallback_answer()` while letting ingestion fail explicitly when embedding is unavailable.

**Tech Stack:** Python, FastAPI service layer, httpx, pytest, existing settings/config pattern

---

## Chunk 1: Breaker Core

### Task 1: Add circuit breaker state machine

**Files:**
- Create: `rag-service/app/services/circuit_breaker.py`
- Modify: `rag-service/app/config.py`
- Test: `rag-service/tests/test_circuit_breaker.py`

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app.services.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker("gemini_llm", failure_threshold=2, recovery_timeout_seconds=30)
    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_breaker_recovers_after_timeout(monkeypatch):
    now = {"value": 100.0}
    breaker = CircuitBreaker(
        "qdrant",
        failure_threshold=1,
        recovery_timeout_seconds=10,
        now_fn=lambda: now["value"],
    )
    breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.before_call()

    now["value"] = 111.0
    breaker.before_call()
    breaker.record_success()
    breaker.before_call()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_circuit_breaker.py`
Expected: FAIL because `circuit_breaker.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic


class CircuitOpenError(RuntimeError):
    ...


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    service_name: str
    failure_threshold: int
    recovery_timeout_seconds: int
    now_fn: callable = monotonic
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        ...

    def record_success(self) -> None:
        ...

    def record_failure(self) -> None:
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_circuit_breaker.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/circuit_breaker.py rag-service/app/config.py rag-service/tests/test_circuit_breaker.py
git commit -m "feat: add process-local circuit breaker core"
```

## Chunk 2: Provider Integration

### Task 2: Guard Gemini LLM and Cohere rerank calls

**Files:**
- Modify: `rag-service/app/services/llm.py`
- Modify: `rag-service/app/services/reranker.py`
- Modify: `rag-service/tests/test_llm_service.py`
- Modify: `rag-service/tests/test_reranker.py`
- Test: `rag-service/tests/test_circuit_breaker.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_generate_short_circuits_when_breaker_open(monkeypatch):
    ...
    with pytest.raises(CircuitOpenError):
        await llm_module.generate("Prompt")


@pytest.mark.asyncio
async def test_reranker_short_circuits_when_breaker_open(monkeypatch):
    ...
    with pytest.raises(CircuitOpenError):
        await service.rerank(query="q", documents=["a"], top_n=1)
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_llm_service.py tests/test_reranker.py tests/test_circuit_breaker.py`
Expected: FAIL because breaker integration is not wired yet.

- [ ] **Step 3: Implement minimal provider guards**

```python
breaker = get_circuit_breaker("gemini_llm")
breaker.before_call()
try:
    response = await client.post(...)
except Exception:
    breaker.record_failure()
    raise
breaker.record_success()
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_llm_service.py tests/test_reranker.py tests/test_circuit_breaker.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/llm.py rag-service/app/services/reranker.py rag-service/tests/test_llm_service.py rag-service/tests/test_reranker.py rag-service/tests/test_circuit_breaker.py
git commit -m "feat: guard llm and reranker with circuit breaker"
```

### Task 3: Guard Gemini embed and Qdrant calls

**Files:**
- Modify: `rag-service/app/services/embedder.py`
- Modify: `rag-service/app/services/vector_store.py`
- Modify: `rag-service/tests/test_embedder.py`
- Modify: `rag-service/tests/test_vector_store.py`
- Test: `rag-service/tests/test_circuit_breaker.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_embedder_short_circuits_when_breaker_open(monkeypatch):
    ...


@pytest.mark.asyncio
async def test_vector_store_search_short_circuits_when_breaker_open(monkeypatch):
    ...
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_embedder.py tests/test_vector_store.py tests/test_circuit_breaker.py`
Expected: FAIL because embedder/vector store still call upstreams directly.

- [ ] **Step 3: Implement minimal guards**

```python
breaker = get_circuit_breaker("gemini_embed")
breaker.before_call()
try:
    response = await _post_with_retry(...)
except Exception:
    breaker.record_failure()
    raise
breaker.record_success()
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_embedder.py tests/test_vector_store.py tests/test_circuit_breaker.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/embedder.py rag-service/app/services/vector_store.py rag-service/tests/test_embedder.py rag-service/tests/test_vector_store.py rag-service/tests/test_circuit_breaker.py
git commit -m "feat: guard embeddings and qdrant with circuit breaker"
```

## Chunk 3: Query Fallback Integration

### Task 4: Preserve query fallbacks when breakers are open

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_query_service_uses_fallback_answer_when_llm_breaker_open(...):
    ...


@pytest.mark.asyncio
async def test_query_service_skips_rerank_when_breaker_open(...):
    ...
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py tests/test_api_endpoints.py`
Expected: FAIL because breaker-open exceptions are not yet treated as controlled fallbacks.

- [ ] **Step 3: Implement minimal fallback handling**

```python
except CircuitOpenError:
    return source_entries, False
```

and

```python
except CircuitOpenError:
    answer = self._fallback_answer(final_sources)
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py tests/test_api_endpoints.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/query.py rag-service/tests/test_query_service.py rag-service/tests/test_api_endpoints.py
git commit -m "feat: add circuit breaker fallbacks to query flow"
```

## Chunk 4: Verification And Checklist

### Task 5: Verify the full slice and update checklist

**Files:**
- Modify: `rag_service_checklist_v3.md`
- Test: `rag-service/tests/test_circuit_breaker.py`
- Test: `rag-service/tests/test_llm_service.py`
- Test: `rag-service/tests/test_reranker.py`
- Test: `rag-service/tests/test_embedder.py`
- Test: `rag-service/tests/test_vector_store.py`
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Run the full relevant test suite**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_circuit_breaker.py tests/test_llm_service.py tests/test_reranker.py tests/test_embedder.py tests/test_vector_store.py tests/test_query_service.py tests/test_api_endpoints.py`
Expected: PASS

- [ ] **Step 2: Update checklist item and short note**

```markdown
- [x] Circuit breaker — Qdrant/Gemini/Cohere/LLM per-service kurallar
  - Ref: `rag-service/app/services/circuit_breaker.py`
  - Akış: `provider boundary -> before_call -> upstream call -> success/failure state update -> query fallback or fast-fail`
```

- [ ] **Step 3: Commit**

```bash
git add rag_service_checklist_v3.md
git commit -m "docs: mark circuit breaker complete"
```
