# Sparse Search Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qdrant tabanlı sparse retrieval'i ingest ve query akışına production-ready şekilde eklemek.

**Architecture:** Dense retrieval mevcut kalır; text chunk'lar için deterministik sparse vector üretilir, Qdrant collection named dense+sparse vector ile güncellenir, `/query` sparse moda alınabildiğinde Qdrant lexical retrieval çalışır. Varsayılan dense davranış korunur.

**Tech Stack:** FastAPI, SQLAlchemy, Qdrant HTTP API, pytest

---

## Chunk 1: Sparse Encoder

### Task 1: Encoder testlerini yaz

**Files:**
- Create: `rag-service/tests/test_sparse_encoder.py`
- Create: `rag-service/app/services/sparse_encoder.py`

- [ ] Step 1: Yazılacak failing testler
- [ ] Step 2: Testleri çalıştır, doğru şekilde fail ettiğini doğrula
- [ ] Step 3: Minimal sparse tokenizer ve vector encoder'ı yaz
- [ ] Step 4: Testleri tekrar çalıştır ve geçir

### Task 2: Encoder davranışını sabitle

**Files:**
- Modify: `rag-service/tests/test_sparse_encoder.py`
- Modify: `rag-service/app/services/sparse_encoder.py`

- [ ] Step 1: Stopword ve boş içerik testlerini ekle
- [ ] Step 2: Testleri fail olarak doğrula
- [ ] Step 3: Minimal düzeltmeleri uygula
- [ ] Step 4: Testleri tekrar çalıştır

## Chunk 2: Vector Store Sparse Support

### Task 3: Collection config testini yaz

**Files:**
- Modify: `rag-service/tests/test_vector_store.py`
- Modify: `rag-service/app/services/vector_store.py`

- [ ] Step 1: Named dense+sparse collection payload testi ekle
- [ ] Step 2: Testi fail olarak çalıştır
- [ ] Step 3: `ensure_collection()` payload'ını sparse destekli hale getir
- [ ] Step 4: Testi tekrar çalıştır

### Task 4: Upsert ve sparse query testlerini yaz

**Files:**
- Modify: `rag-service/tests/test_vector_store.py`
- Modify: `rag-service/app/services/vector_store.py`

- [ ] Step 1: Sparse vector alanının upsert payload'ına yazıldığını test et
- [ ] Step 2: Sparse query payload testini ekle
- [ ] Step 3: Testleri fail olarak çalıştır
- [ ] Step 4: `upsert_chunks()` ve yeni `search_sparse_chunks()` implement et
- [ ] Step 5: Testleri tekrar çalıştır

## Chunk 3: Ingestion Sparse Indexing

### Task 5: Ingestion testini yaz

**Files:**
- Modify: `rag-service/tests/test_ingestion_service.py`
- Modify: `rag-service/app/services/ingestion.py`

- [ ] Step 1: Text chunk upsert payload'ında sparse vector üretildiğini test et
- [ ] Step 2: Testi fail olarak çalıştır
- [ ] Step 3: Ingestion içinde sparse encoder entegrasyonunu ekle
- [ ] Step 4: Testi tekrar çalıştır

## Chunk 4: Query Sparse Mode

### Task 6: Schema ve API testini yaz

**Files:**
- Modify: `rag-service/app/schemas/query.py`
- Modify: `rag-service/tests/test_api_endpoints.py`

- [ ] Step 1: `/query` için `retrieval_mode=sparse` request testi ekle
- [ ] Step 2: Testi fail olarak çalıştır
- [ ] Step 3: Request schema'ya opsiyonel retrieval mode alanını ekle
- [ ] Step 4: Testi tekrar çalıştır

### Task 7: Query service sparse branch testini yaz

**Files:**
- Modify: `rag-service/tests/test_query_service.py`
- Modify: `rag-service/app/services/query.py`

- [ ] Step 1: `QueryService` sparse modda `search_sparse_chunks()` çağırıyor testini ekle
- [ ] Step 2: Sparse sonuçta `retrieval_mode=sparse_qdrant` döndüğünü test et
- [ ] Step 3: Testleri fail olarak çalıştır
- [ ] Step 4: Query service sparse branch implement et
- [ ] Step 5: Testleri tekrar çalıştır

## Chunk 5: Verification And Checklist

### Task 8: Hedef test paketini çalıştır

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] Step 1: `tests/test_sparse_encoder.py`
- [ ] Step 2: `tests/test_vector_store.py`
- [ ] Step 3: `tests/test_api_endpoints.py`
- [ ] Step 4: `tests/test_query_service.py`
- [ ] Step 5: Gerekliyse ingestion test paketini çalıştır
- [ ] Step 6: `Sparse search` maddesini checklist'te işaretle
