# Query Expansion Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-ready query expansion layer that uses deterministic synonyms by default and optional LLM rewrite for retrieval-only expansion.

**Architecture:** Introduce a focused `QueryExpansionService` that builds an `expanded_query` before retrieval. Keep answer generation bound to the original user question, and treat LLM rewrite as an optional, fail-safe enhancement on top of synonym expansion.

**Tech Stack:** Python, existing FastAPI service layer, current `llm.py`, pytest

---

## Chunk 1: Expansion Core

### Task 1: Add deterministic query expansion service

**Files:**
- Create: `rag-service/app/services/query_expansion.py`
- Modify: `rag-service/tests/test_query_expansion.py`

- [ ] **Step 1: Write the failing expansion tests**

```python
async def test_query_expansion_adds_synonyms():
    result = await service.expand("invoice renewal")
    assert "billing" in result.expanded_query
    assert "contract renewal" in result.expanded_query
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_expansion.py`
Expected: FAIL because `query_expansion.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass
class ExpandedQuery:
    original_question: str
    expanded_query: str
    synonyms_applied: list[str]
    rewrite_applied: bool


class QueryExpansionService:
    async def expand(self, question: str, *, use_llm: bool = False) -> ExpandedQuery:
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_expansion.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/query_expansion.py rag-service/tests/test_query_expansion.py
git commit -m "feat: add deterministic query expansion service"
```

### Task 2: Add config and optional LLM rewrite fallback behavior

**Files:**
- Modify: `rag-service/app/config.py`
- Modify: `rag-service/app/services/query_expansion.py`
- Modify: `rag-service/tests/test_query_expansion.py`

- [ ] **Step 1: Write the failing LLM rewrite tests**

```python
async def test_query_expansion_uses_llm_rewrite_when_enabled(...):
    assert result.rewrite_applied is True


async def test_query_expansion_falls_back_to_synonyms_when_llm_fails(...):
    assert result.rewrite_applied is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_expansion.py -k rewrite`
Expected: FAIL because rewrite config/behavior does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
query_expansion_use_llm: bool = False
query_expansion_max_terms: int = 5
```

and

```python
if use_llm:
    try:
        rewritten = await generate(...)
    except Exception:
        rewritten = synonym_query
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_expansion.py -k rewrite`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/config.py rag-service/app/services/query_expansion.py rag-service/tests/test_query_expansion.py
git commit -m "feat: add optional llm rewrite for query expansion"
```

## Chunk 2: QueryService Integration

### Task 3: Use expanded query for retrieval while preserving original prompt question

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Write the failing integration tests**

```python
async def test_query_service_uses_expanded_query_for_retrieval(...):
    assert captured["embed_question"] == "invoice billing payment"


async def test_query_service_uses_original_question_for_answer_prompt(...):
    assert captured["prompt_question"] == "invoice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k expansion`
Expected: FAIL because QueryService still uses the raw question everywhere.

- [ ] **Step 3: Write minimal integration**

```python
expanded = await self.query_expansion.expand(question, use_llm=...)
query_embedding = await embed_query_text(expanded.expanded_query)
...
sparse_hits = await self._sparse_ranked_document_ids(... question=expanded.expanded_query ...)
...
prompt = build_query_answer_prompt(question=question, sources=final_sources)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k expansion`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/query.py rag-service/tests/test_query_service.py
git commit -m "feat: use expanded query for retrieval"
```

## Chunk 3: Verification And Checklist

### Task 4: Run focused verification and update checklist

**Files:**
- Modify: `rag_service_checklist_v3.md`
- Test: `rag-service/tests/test_query_expansion.py`
- Test: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Run focused verification**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_expansion.py tests/test_query_service.py -k expansion`
Expected: PASS

- [ ] **Step 2: Update checklist item and short note**

```markdown
- [x] Query expansion — sinonim sözlüğü + LLM genişletme — Ref: `rag-service/app/services/query_expansion.py`, `rag-service/app/services/query.py` | Akış: `question -> synonym expand -> optional llm rewrite -> retrieval input`
```

- [ ] **Step 3: Commit**

```bash
git add rag_service_checklist_v3.md
git commit -m "docs: mark query expansion complete"
```
