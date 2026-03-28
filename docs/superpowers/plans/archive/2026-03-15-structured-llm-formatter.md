# Structured LLM Formatter Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `structured` ingest send arbitrary JSON records to an LLM for semantic rewriting before chunk/embed/upsert, with rule-based fallback if LLM formatting is unavailable.

**Architecture:** Add a dedicated semantic formatter service that calls Gemini `generateContent` with a constrained prompt and returns normalized text plus formatter metadata. Update the structured loader to call that service first and fall back to the existing rule-based formatter when no API key exists or the semantic formatter fails.

**Tech Stack:** FastAPI service layer, httpx, Gemini REST API, pytest, existing structured loader and ingestion pipeline

---

### Task 1: Add semantic formatter contract tests

**Files:**
- Modify: `rag-service/tests/test_summary_formatter.py`
- Modify: `rag-service/tests/test_loaders.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run targeted tests to verify failure**
- [ ] **Step 3: Implement minimal semantic formatter service and loader wiring**
- [ ] **Step 4: Re-run targeted tests to verify pass**

### Task 2: Persist semantic formatter metadata in structured ingest

**Files:**
- Modify: `rag-service/tests/test_ingestion_service.py`
- Modify: `rag-service/app/services/loaders.py`
- Modify: `rag-service/app/services/ingestion.py`

- [ ] **Step 1: Write the failing service test**
- [ ] **Step 2: Run targeted test to verify failure**
- [ ] **Step 3: Implement minimal metadata propagation**
- [ ] **Step 4: Re-run targeted test to verify pass**

### Task 3: Full verification

**Files:**
- Test: `rag-service/tests/test_summary_formatter.py`
- Test: `rag-service/tests/test_loaders.py`
- Test: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Run focused tests**
- [ ] **Step 2: Run full suite**
