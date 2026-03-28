# Confidence Score Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `confidence_score` and `confidence_warning` to query/chat responses using normalized final source scores and a low-confidence warning threshold.

**Architecture:** Keep confidence calculation inside `QueryService`, next to final source selection, so it operates on the same source list the user sees. Extend response schemas only; do not inject warnings into `answer` text or change prompt behavior.

**Tech Stack:** Python, Pydantic, FastAPI response models, pytest

---

## Chunk 1: Response Contract

### Task 1: Extend query/chat response schemas

**Files:**
- Modify: `rag-service/app/schemas/query.py`
- Modify: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Write the failing API/schema test**

```python
def test_query_response_includes_confidence_fields(...):
    assert payload["confidence_score"] == 0.42
    assert payload["confidence_warning"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py -k confidence`
Expected: FAIL because response model does not expose the new fields yet.

- [ ] **Step 3: Write minimal schema implementation**

```python
class QueryResponse(BaseModel):
    ...
    confidence_score: float | None = None
    confidence_warning: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_api_endpoints.py -k confidence`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/schemas/query.py rag-service/tests/test_api_endpoints.py
git commit -m "feat: add confidence fields to query responses"
```

## Chunk 2: Confidence Calculation

### Task 2: Add normalized confidence calculation to QueryService

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] **Step 1: Write the failing query service tests**

```python
async def test_query_service_returns_confidence_score_from_source_scores(...):
    assert result["confidence_score"] == pytest.approx(0.5, rel=1e-3)
    assert result["confidence_warning"] is None


async def test_query_service_warns_when_confidence_is_low(...):
    assert result["confidence_score"] < 0.35
    assert result["confidence_warning"] == "Bu yanit dusuk guvenle olusturuldu; kaynaklari kontrol edin."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k confidence`
Expected: FAIL because query responses do not calculate confidence yet.

- [ ] **Step 3: Write minimal implementation**

```python
def _normalize_confidence_score(self, score: float) -> float:
    if score <= 1.0:
        return max(0.0, score)
    return score / (score + 1.0)


def _build_confidence(self, source_entries):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k confidence`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/query.py rag-service/tests/test_query_service.py
git commit -m "feat: calculate response confidence score"
```

### Task 3: Preserve empty/no-score behavior

**Files:**
- Modify: `rag-service/tests/test_query_service.py`
- Modify: `rag-service/app/services/query.py`

- [ ] **Step 1: Write the failing empty/no-score tests**

```python
async def test_query_service_returns_none_confidence_for_empty_result(...):
    assert result["confidence_score"] is None
    assert result["confidence_warning"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k "empty and confidence"`
Expected: FAIL because empty response path does not include the new fields.

- [ ] **Step 3: Write minimal implementation**

```python
if not top_documents:
    return {
        ...,
        "confidence_score": None,
        "confidence_warning": None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py -k "empty and confidence"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/query.py rag-service/tests/test_query_service.py
git commit -m "feat: handle empty confidence response"
```

## Chunk 3: Verification And Checklist

### Task 4: Run focused verification and update checklist

**Files:**
- Modify: `rag_service_checklist_v3.md`
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [ ] **Step 1: Run the focused suite**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_query_service.py tests/test_api_endpoints.py -k confidence`
Expected: PASS

- [ ] **Step 2: Update checklist item and short note**

```markdown
- [x] Confidence score — top chunk score ortalaması, düşükse uyarı — Ref: `rag-service/app/services/query.py`, `rag-service/app/schemas/query.py` | Akış: `final source scores -> normalize -> average -> confidence_score + optional warning`
```

- [ ] **Step 3: Commit**

```bash
git add rag_service_checklist_v3.md
git commit -m "docs: mark confidence score complete"
```
