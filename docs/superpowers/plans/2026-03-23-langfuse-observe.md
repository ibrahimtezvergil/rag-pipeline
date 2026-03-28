# Langfuse Observe Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FastAPI agir endpoint'leri ve kritik retrieval/ingestion servislerine best-effort Langfuse tracing eklemek.

**Architecture:** Optional bir tracing adapter'i `langfuse.observe` ve metadata update akisini no-op fallback ile saracak. Endpoint seviyesinde root trace, servis seviyesinde child observation kullanilacak; ham query/prompt/content hicbir noktada Langfuse'a gonderilmeyecek.

**Tech Stack:** FastAPI, Langfuse Python SDK (optional), existing service layer, pytest

---

## Chunk 1: Tracing Adapter

### Task 1: Test-first tracing helper

**Files:**
- Create: `rag-service/app/services/tracing.py`
- Create: `rag-service/tests/test_tracing.py`
- Modify: `rag-service/app/config.py`
- Modify: `rag-service/requirements.txt`

- [ ] Step 1: Write failing tracing tests for no-op decorator and metadata helper
- [ ] Step 2: Run `pytest -q tests/test_tracing.py` and verify failure
- [ ] Step 3: Implement optional Langfuse adapter with lazy import and safe no-op fallback
- [ ] Step 4: Add config fields for Langfuse host/public/secret keys
- [ ] Step 5: Re-run `pytest -q tests/test_tracing.py`

## Chunk 2: Endpoint Tracing

### Task 2: Instrument heavy FastAPI endpoints

**Files:**
- Modify: `rag-service/app/api/query.py`
- Modify: `rag-service/app/api/ingest.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [ ] Step 1: Write failing API tests asserting tracing metadata hook is called without raw request text
- [ ] Step 2: Run `pytest -q tests/test_api_endpoints.py -k tracing`
- [ ] Step 3: Add `@observe` to `/query`, `/chat`, `/ingest`, `/ingest/batch`
- [ ] Step 4: Add endpoint-level metadata updates using only safe fields
- [ ] Step 5: Re-run `pytest -q tests/test_api_endpoints.py -k tracing`

## Chunk 3: Service Spans

### Task 3: Instrument query and ingestion services

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_query_service.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: Write failing tests for query/ingestion trace metadata updates
- [ ] Step 2: Run focused pytest commands and verify failure
- [ ] Step 3: Add `@observe` and metadata updates to query/ingestion services
- [ ] Step 4: Re-run focused pytest commands

### Task 4: Instrument provider boundaries

**Files:**
- Modify: `rag-service/app/services/llm.py`
- Modify: `rag-service/app/services/embedder.py`
- Modify: `rag-service/app/services/reranker.py`
- Modify: `rag-service/tests/test_llm_service.py`
- Modify: `rag-service/tests/test_embedder.py`
- Modify: `rag-service/tests/test_reranker.py`

- [ ] Step 1: Write failing tests for generation/embedding/rerank metadata updates
- [ ] Step 2: Run focused pytest commands and verify failure
- [ ] Step 3: Add tracing decorators and metadata updates at provider boundaries
- [ ] Step 4: Re-run focused pytest commands

## Chunk 4: Verification and Checklist

### Task 5: Verify integrated behavior and update checklist

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: Run focused suite covering tracing helper, API, query, ingestion, llm, embedder, reranker
- [ ] Step 2: Update checklist item `FastAPI pipeline'larına @observe decorator`
- [ ] Step 3: Summarize environment limits if full integration DB suite cannot run
