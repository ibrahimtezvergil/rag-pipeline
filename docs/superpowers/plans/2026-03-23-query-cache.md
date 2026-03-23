# Query Cache Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redis-backed query cache ve project-level invalidation eklemek.

**Architecture:** `QueryService` cevaplarini Redis'e JSON olarak cache'ler; key fingerprint request-shaping alanlari ve tenant/project scope'u icerir. `IngestionService` basarili re-index veya delete sonrasinda ilgili project cache set'ini temizler.

**Tech Stack:** FastAPI, redis.asyncio, existing query/ingestion services, pytest

---

## Chunk 1: Cache Service

### Task 1: Query cache helper'ini TDD ile ekle

**Files:**
- Create: `rag-service/app/services/query_cache.py`
- Create: `rag-service/tests/test_query_cache.py`
- Modify: `rag-service/app/config.py`

- [ ] Step 1: Failing tests yaz (`build_key`, `get/set`, `invalidate_project`, fail-open)
- [ ] Step 2: `pytest -q tests/test_query_cache.py` ile fail'i gor
- [ ] Step 3: Minimal Redis cache helper implement et
- [ ] Step 4: TTL config ekle
- [ ] Step 5: `pytest -q tests/test_query_cache.py` ile green al

## Chunk 2: Query Integration

### Task 2: QueryService cache hit/miss davranisini ekle

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] Step 1: Cache hit ve miss icin failing tests yaz
- [ ] Step 2: Focused pytest ile fail'i gor
- [ ] Step 3: `QueryService` icine cache dependency ve early-return cache path ekle
- [ ] Step 4: Success path sonunda cache write ekle
- [ ] Step 5: Focused pytest ile green al

## Chunk 3: Invalidation Integration

### Task 3: Ingestion success/delete invalidation

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: Successful ingest ve delete icin failing invalidation tests yaz
- [ ] Step 2: Focused pytest ile fail'i gor
- [ ] Step 3: `IngestionService` icine cache dependency ekle ve invalidate et
- [ ] Step 4: Focused pytest ile green al

## Chunk 4: Checklist and Verification

### Task 4: Verify touched area and close checklist items

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: Focused suite calistir (`test_query_cache`, `test_query_service`, `test_ingestion_service`, gerekliyse API tests)
- [ ] Step 2: Checklist'te `Query cache` ve `Cache invalidation` maddelerini kapat
- [ ] Step 3: Environment limit varsa not et
