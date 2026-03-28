# Observability Logging Implementation Plan

## Status: COMPLETED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingestion ve query akışlarına production-ready structured JSON stdout logging eklemek ve query içeriğini hash ile gizlemek.

**Architecture:** Yeni `observability.py` helper'ı standart `logging` + `json.dumps` ile event payload üretir. `IngestionService` per-chunk `ingestion.chunk_indexed` event'leri emit eder; `QueryService` query tamamlandığında `query.completed` event'i yazar. Query içeriği düz metin loglanmaz, deterministic `sha256` hash loglanır.

**Tech Stack:** Python logging, json, hashlib, FastAPI service layer, pytest

---

## Chunk 1: Observability Helper

### Task 1: Helper testlerini yaz

**Files:**
- Create: `rag-service/app/services/observability.py`
- Create: `rag-service/tests/test_observability.py`

- [ ] Step 1: JSON event payload'ının `logger.info()` ile string olarak yazıldığını doğrulayan failing testleri yaz
- [ ] Step 2: Deterministic query hash üretimini doğrulayan failing test ekle
- [ ] Step 3: Testleri çalıştır ve beklenen şekilde fail ettiğini doğrula
- [ ] Step 4: Minimal `emit_event()` ve `hash_query()` helper'larını implement et
- [ ] Step 5: `tests/test_observability.py` dosyasını tekrar çalıştır ve geçir

## Chunk 2: Ingestion Logging

### Task 2: Per-chunk ingestion log testini yaz

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] Step 1: Her chunk için `ingestion.chunk_indexed` event'i üretildiğini doğrulayan failing test ekle
- [ ] Step 2: Payload içinde `chunk_index`, `modality`, `embed_ms`, `token_count`, `vector_dimension` alanlarını doğrulayan test ekle
- [ ] Step 3: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 4: Ingestion tarafında `time.perf_counter()` ölçümü ve per-chunk event emission ekle
- [ ] Step 5: `token_count = len(content) // 4` tahminini nullable olacak şekilde uygula
- [ ] Step 6: İlgili ingestion testlerini tekrar çalıştır ve geçir

## Chunk 3: Query Logging

### Task 3: Query completed log testini yaz

**Files:**
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/tests/test_query_service.py`

- [ ] Step 1: `query.completed` event'i üretildiğini doğrulayan failing test ekle
- [ ] Step 2: `query_hash`, `retrieval_mode`, `reranker_ms`, `llm_ms`, `top_chunk_score`, `source_count` alanlarını doğrulayan test ekle
- [ ] Step 3: Ham query'nin log payload'ında bulunmadığını doğrulayan test ekle
- [ ] Step 4: Testleri çalıştır ve fail ettiğini doğrula
- [ ] Step 5: Query akışına hash üretimi ve `query.completed` event emission ekle
- [ ] Step 6: LLM ve reranker sürelerini `time.perf_counter()` ile ölç; yoksa `null` bırak
- [ ] Step 7: Query service testlerini tekrar çalıştır ve geçir

## Chunk 4: Verification And Checklist

### Task 4: Hedef test paketini çalıştır

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: `tests/test_observability.py`
- [ ] Step 2: `tests/test_ingestion_service.py`
- [ ] Step 3: `tests/test_query_service.py`
- [ ] Step 4: Gerekirse `tests/test_api_endpoints.py` ile regresyon doğrula
- [ ] Step 5: Ortam izin veriyorsa integration testleri çalıştır; izin yoksa blokajı not et
- [ ] Step 6: Checklist'te şu üç maddeyi işaretle:
- [ ] Step 7: `Structured JSON log — ingestion`
- [ ] Step 8: `Structured JSON log — query`
- [ ] Step 9: `Query içeriği loglanmaz — sadece SHA256 hash (GDPR)`
