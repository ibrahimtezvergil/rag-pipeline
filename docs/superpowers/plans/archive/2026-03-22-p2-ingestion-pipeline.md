# RAG Service P2 Ingestion Pipeline — Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete ingestion pipeline: source loaders (PDF, web, image, structured), chunker, Gemini Embedding 2 embedder, BM25 sparse encoder, Qdrant upsert, ARQ async worker, and the `/ingest` REST endpoint.

**Architecture:** Each ingest request creates a `RagIngestionJob` row. In `sync` mode the full pipeline runs in the request. In `async` mode an ARQ job is enqueued and returns 202. The pipeline: load source → chunk → embed (dense + sparse) → upsert Qdrant → save chunk rows → update job status.

**Tech Stack:** Gemini API (`gemini-embedding-2-preview`), Qdrant REST, ARQ + Redis, pymupdf (PyMuPDF), httpx, crawl4ai, rank_bm25, nltk (Snowball)

---

## Scope Note

This is **Plan 2 of 3** for P1 Core Infrastructure:
- **Plan 1:** Foundation — project skeleton, Docker, DB schema, auth, health ✅
- **Plan 2 (this):** Ingestion Pipeline
- **Plan 3:** Query Pipeline — hybrid search, Cohere rerank, `/query`, `/chat`, LangGraph

Spec: `rag_service_plan_v3.md` + `rag_service_checklist_v3.md`

---

## Key Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Embed model | `gemini-embedding-2-preview` | Natively multimodal — text, image, PDF in one API |
| Embed dimension | 768 (MRL truncated) | Storage/quality balance; pass `output_dimensionality=768` |
| Sparse encode | BM25 + Snowball Turkish stemmer | Language-aware keyword matching |
| Chunk strategy | text=512tok/128overlap, pdf=layout-aware, parent-child | Semantic coherence + retrieval recall |
| Content hash | SHA256 per document + per chunk | Dedup, re-index optimization |
| Parent sentinel | `__PARENT_INDEX__:N` in chunk text | FK resolved in repository layer before DB write |
| Async queue | ARQ + Redis | Retries, backoff, separate IO/CPU worker pools |

---

## Critical Implementation Patterns

### 1. Gemini Embedding 2 — text embed
```python
# app/services/embedder.py
import google.generativeai as genai

genai.configure(api_key=settings.gemini_api_key)

async def embed_text_content(text: str) -> list[float]:
    result = genai.embed_content(
        model=settings.embed_model,          # "gemini-embedding-2-preview"
        content=text,
        output_dimensionality=settings.embed_dimension,  # 768
    )
    return result["embedding"]
```

### 2. Gemini Embedding 2 — image embed
```python
# Pass image as Part with inline_data
import PIL.Image, io

async def embed_image_content(image_bytes: bytes) -> list[float]:
    image = PIL.Image.open(io.BytesIO(image_bytes))
    result = genai.embed_content(
        model=settings.embed_model,
        content=image,
        output_dimensionality=settings.embed_dimension,
    )
    return result["embedding"]
```

### 3. Gemini Embedding 2 — PDF native (≤6 pages)
```python
# Pass PDF bytes as Part with inline_data mime_type="application/pdf"
import google.generativeai.types as genai_types

async def resolve_pdf_embedding(pdf_bytes: bytes) -> list[float]:
    part = genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    result = genai.embed_content(
        model=settings.embed_model,
        content=part,
        output_dimensionality=settings.embed_dimension,
    )
    return result["embedding"]
```

### 4. Sparse encode — BM25 Snowball
```python
# app/services/sparse_encoder.py
from rank_bm25 import BM25Okapi
from nltk.stem import SnowballStemmer

stemmer = SnowballStemmer("turkish")

def tokenize(text: str) -> list[str]:
    return [stemmer.stem(w) for w in text.lower().split()]

def encode_sparse_text(text: str, vocab_size: int = 30000) -> dict[int, float]:
    tokens = tokenize(text)
    freq: dict[int, float] = {}
    for tok in tokens:
        idx = hash(tok) % vocab_size
        freq[idx] = freq.get(idx, 0.0) + 1.0
    total = sum(freq.values()) or 1.0
    return {k: v / total for k, v in freq.items()}
```

### 5. Qdrant upsert — named vectors
```python
# Qdrant collection has BOTH dense and sparse named vectors
# Dense: "dense" (size=768, distance=Cosine)
# Sparse: "sparse" (SparseVectors)

# Upsert point:
{
    "id": str(chunk_id),
    "vector": {
        "dense": [0.1, 0.2, ...],       # 768-dim float list
        "sparse": {
            "indices": [123, 456, ...],
            "values": [0.8, 0.2, ...],
        }
    },
    "payload": {
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "document_id": str(document_id),
        "chunk_id": str(chunk_id),
        "scope_type": "...",
        "scope_id": "...",
        "modality": "text",
        "content": "...",
        "title": "...",
        "source_ref": "...",
        "page_number": None,
        "tags": [],
        "acl": [],
        "snapshot_date": None,
    }
}
```

### 6. Parent-child chunk sentinel
```python
# Chunker emits parent chunk with text = "__PARENT_INDEX__:0"
# Repository resolves the sentinel → actual parent_chunk_id UUID after DB insert
# See: app/repositories/ingestion.py — save_chunks()
```

### 7. Content hash dedup
```python
import hashlib

def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()

# Document level: hash of raw source content
# Chunk level: hash of chunk text
# On re-ingest: compare hashes → skip unchanged chunks
```

---

## Tasks

### Task 1 — Source Loaders
- [ ] `app/services/loaders.py` — `load_source(source_type, ...)` dispatcher
- [ ] PDF loader — ≤6 pages: Gemini direct PDF path; >6 pages: pymupdf layout-aware text extraction
  - `fitz.open(stream=pdf_bytes)` for layout blocks
  - Pass `source_filename` for metadata
- [ ] Web loader — `crawl4ai` with JS render, nav/footer stripping, static httpx fallback
  - `AsyncWebCrawler` → `CrawlResult.markdown`
  - Strip boilerplate before chunking
- [ ] Image loader — detect MIME (PNG/JPEG/WebP), call `embed_image_content`
  - `app/services/media.py` — `detect_image_mime_type`, `load_binary_source`
- [ ] Structured loader — `records: list[dict]` → `SummaryFormatter` → text embed
  - Rule-based fallback if LLM call fails
- [ ] `decode_base64_source(source_ref)` utility — strip `data:...;base64,` prefix, decode bytes
- [ ] **Skip:** Audio loader (not implemented — 120s clip split deferred), DB loader (disabled — tenant isolation pending)

**Test:** `tests/test_loaders.py` — mock httpx/crawl4ai, assert content/metadata shape

---

### Task 2 — Chunker
- [ ] `app/services/chunking.py` — `build_chunks(content, source_type, metadata) -> list[ChunkData]`
- [ ] Text strategy: 512 token window, 128 token overlap (tiktoken or char-based)
- [ ] PDF strategy: pymupdf layout blocks → preserve page_number + bbox per chunk
- [ ] Parent chunk: first chunk of each source = parent, rest = children with `parent_chunk_id` sentinel `__PARENT_INDEX__:0`
- [ ] Quality filter: skip empty, min 20 chars, max 8000 chars; deduplicate exact matches
- [ ] `ChunkData` dataclass: `text`, `parent_index`, `page_number`, `bbox`, `section_title`, `modality`

**Test:** `tests/test_chunking.py` — assert chunk count, parent sentinel, page_number propagation

---

### Task 3 — Embedder
- [ ] `app/services/embedder.py`
- [ ] `embed_text_content(text: str) -> list[float]` — Gemini text embed, `output_dimensionality=768`
- [ ] `embed_image_content(image_bytes: bytes) -> list[float]` — PIL Image → Gemini
- [ ] `resolve_pdf_embedding(pdf_bytes: bytes, page_count: int) -> list[float] | None`
  - ≤6 pages: native PDF embed
  - >6 pages: return None (caller falls back to pymupdf text chunking)
- [ ] `embed_query_text(text: str) -> list[float]` — same model, query task type

**Note:** Gemini API is synchronous (`genai.embed_content`). Wrap in `asyncio.to_thread()` or use `run_in_executor` if needed for async contexts.

**Test:** `tests/test_embedder.py` — monkeypatch `genai.embed_content`, assert dimension=768

---

### Task 4 — Sparse Encoder
- [ ] `app/services/sparse_encoder.py`
- [ ] `encode_sparse_text(text: str, vocab_size=30000) -> dict[int, float]`
- [ ] Turkish Snowball stemmer (nltk) for tokenization
- [ ] Output: `{token_hash % vocab_size: normalized_tf}` — matches Qdrant sparse vector format

**Test:** `tests/test_sparse_encoder.py` — assert non-empty output, values sum to ~1.0, Turkish stem coverage

---

### Task 5 — Qdrant Vector Store
- [ ] `app/services/vector_store.py` — `QdrantVectorStore`
- [ ] `ensure_collection(name)` — PUT `/collections/{name}` with dense + sparse config (idempotent)
  ```json
  {
    "vectors": {"size": 768, "distance": "Cosine"},
    "sparse_vectors": {"sparse": {}}
  }
  ```
- [ ] `upsert_chunks(collection, points)` — POST `/collections/{name}/points`
- [ ] `search_dense(collection, vector, filter, limit)` — POST `/collections/{name}/points/search`
- [ ] `search_sparse(collection, sparse_vector, filter, limit)` — POST with `sparse_vector` query
- [ ] Payload filter builder — `must: [{key: "tenant_id", match: {value: ...}}, ...]`
- [ ] `delete_by_document_id(collection, document_id)` — DELETE points by payload filter

**Critical:** Use Qdrant REST API directly (httpx) — not the Python client library (version compatibility issues).

**Test:** `tests/test_vector_store.py` — monkeypatch httpx, assert request payloads

---

### Task 6 — Ingestion Repository
- [ ] `app/repositories/ingestion.py` — `IngestionRepository(session)`
- [ ] `create_document(payload) -> RagDocument`
- [ ] `save_chunks(document_id, chunks) -> list[RagChunk]`
  - Resolve `__PARENT_INDEX__:N` sentinel → actual `parent_chunk_id` UUID
  - Insert all chunks in one `session.execute(insert(RagChunk).values(...))`
- [ ] `create_ingestion_job(payload) -> RagIngestionJob`
- [ ] `update_job_status(job_id, status, error_message, chunks_processed, duration_ms)`
- [ ] `get_job(job_id) -> RagIngestionJob | None`
- [ ] `delete_job(job_id)` — cascade deletes document + chunks + Qdrant points

**Test:** `tests/test_ingestion_repository.py` (integration) — uses `integration_session` fixture

---

### Task 7 — Ingestion Service
- [ ] `app/services/ingestion.py` — `IngestionService(session, dispatcher, vector_store)`
- [ ] `create_ingestion_job(payload, project_id)` — sync or async branch
  - Sync: run full pipeline inline, return result
  - Async: create job row, enqueue ARQ task, return job_id
- [ ] `_run_pipeline(job_id, payload, project_id)`:
  1. `load_source(...)` → `content`, `metadata`
  2. `build_chunks(content, source_type, metadata)` → `list[ChunkData]`
  3. For each chunk: `embed_text_content` + `encode_sparse_text`
  4. `vector_store.upsert_chunks(collection, points)`
  5. `repository.save_chunks(document_id, chunks)`
  6. `repository.update_job_status(job_id, "completed", ...)`
- [ ] `get_ingestion_job(job_id)` — fetch job row, return status dict
- [ ] `delete_ingestion_job(job_id)` — delete job + document + chunks + Qdrant points
- [ ] `create_ingestion_batch(items, project_id)` — async only, enqueue N jobs

**Test:** `tests/test_ingestion_service.py` — monkeypatch embedder + vector_store, assert job status

---

### Task 8 — ARQ Worker
- [ ] `workers/tasks/ingest.py` — `ingest_document(ctx, job_id, payload_dict, project_id_str)`
  - Deserialize payload, call `IngestionService._run_pipeline`
  - On exception: `update_job_status(job_id, "failed", error_message=str(e))`
  - Max 3 retries with exponential backoff (`arq` retry mechanism)
- [ ] `workers/main.py` — `WorkerSettings`
  - `functions = [ingest_document]`
  - `redis_settings = RedisSettings.from_dsn(settings.redis_url)`
  - `max_jobs = 10`
- [ ] `app/services/dispatch.py` — `IngestionDispatcher` / `NullIngestionDispatcher`
  - `NullIngestionDispatcher.enqueue(job_id, payload)` — runs inline (sync mode)
  - `ArqIngestionDispatcher.enqueue(job_id, payload)` — enqueues to Redis

**Test:** `tests/test_worker_ingest.py` — mock redis, assert retry on failure

---

### Task 9 — `/ingest` API Endpoint
- [ ] `app/api/ingest.py` — `APIRouter`
- [ ] `POST /ingest` → `IngestResponse` (201 sync, 202 async)
- [ ] `POST /ingest/batch` → `IngestBatchResponse` (202, async only)
- [ ] `GET /ingest/{job_id}` → `IngestStatusResponse`
- [ ] `DELETE /ingest/{job_id}` → 204
- [ ] `mode` query param override (`?mode=sync` forces sync)
- [ ] Service injected via `Depends(_get_ingestion_service)` — see session leak fix below

**Critical:** `_get_ingestion_service` MUST use `Depends(get_db_session)`:
```python
def _get_ingestion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestionService:
    service = getattr(request.app.state, "ingestion_service", None)
    if service is not None:
        return service
    dispatcher = getattr(request.app.state, "ingestion_dispatcher", None)
    return IngestionService(session, dispatcher=dispatcher)
```
**Never** call `AsyncSessionLocal()` directly — the session will never be closed.

**Test:** `tests/test_api_endpoints.py` — inject mock service via `app.state.ingestion_service`

---

### Task 10 — Schemas
- [ ] `app/schemas/ingest.py`
  - `IngestRequest`: `source_type`, `source_ref?`, `source_bytes_b64?`, `source_filename?`, `source_sql?`, `records?`, `title?`, `scope_type?`, `scope_id?`, `entity_type?`, `origin?`, `entity_id?`, `record_ids?`, `snapshot_date?`, `tags?`, `acl?`, `collection?`, `mode: "sync"|"async"="async"`
  - `IngestResponse`: `job_id`, `status`, `mode`, `document_id?`, `chunk_count?`, `duration_ms?`
  - `IngestStatusResponse`: `job_id`, `status`, `error_message?`, `chunks_processed?`, `duration_ms?`
  - `IngestBatchRequest`: `items: list[IngestRequest]`
  - `IngestBatchResponse`: `items: list[IngestResponse]`

---

## Verification

After all tasks complete:

```bash
# Start stack
docker compose up -d postgres qdrant redis

# Run unit tests
pytest tests/ -q

# Manual smoke test
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: test-key-1" \
  -H "X-Project-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"source_type": "text", "source_ref": "Hello world chunk.", "mode": "sync"}'

# Check job status
curl http://localhost:8000/ingest/<job_id> \
  -H "X-API-Key: test-key-1" -H "X-Project-ID: <uuid>"
```

Expected: job status = `completed`, chunk_count ≥ 1, Qdrant collection has the point.
