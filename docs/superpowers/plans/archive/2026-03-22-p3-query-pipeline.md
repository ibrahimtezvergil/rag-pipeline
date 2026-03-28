# RAG Service P3 Query Pipeline — Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete query pipeline: hybrid search (dense + sparse → RRF fusion → Cohere Rerank), parent context expansion, `/query` endpoint, Redis-backed `/chat` endpoint with conversation history, and optional LangGraph Self-RAG.

**Architecture:** Query → embed question → search Qdrant (dense + sparse in parallel) → RRF merge → fetch parent chunks → Cohere Rerank-3 → build prompt → LLM answer. Chat adds Redis session history (6 turns, TTL 30min) before the query pipeline.

**Tech Stack:** Qdrant REST, Gemini Embedding 2, Cohere Rerank-3 API, Redis (async), LangGraph (optional), httpx

---

## Scope Note

This is **Plan 3 of 3** for P1 Core Infrastructure:
- **Plan 1:** Foundation — project skeleton, Docker, DB schema, auth, health ✅
- **Plan 2:** Ingestion Pipeline — loaders, chunker, embed, Qdrant upsert, ARQ ✅
- **Plan 3 (this):** Query Pipeline

Spec: `rag_service_plan_v3.md` + `rag_service_checklist_v3.md`

---

## Key Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Retrieval | Dense + Sparse → RRF → Rerank | Keyword recall + semantic precision |
| Dense search | Qdrant `/points/search` with named vector `"dense"` | Cosine similarity |
| Sparse search | Qdrant `/points/search` with `sparse_vector` | BM25 keyword match |
| RRF k | 60 | Standard RRF reciprocal rank constant |
| Reranker | Cohere Rerank-3 (`rerank-v3.5`) | Best-in-class cross-encoder |
| Parent context | Fetch parent chunk text for each retrieved child | More coherent context window |
| Tenant filter | `must: [{tenant_id}, {project_id}]` in every search | Hard isolation |
| Conversation | Redis `list` per `session_id`, trim to last 6 turns, TTL 30min | Stateless API, stateful session |
| LangGraph | Config toggle `use_graph: true/false` | Optional; disabled by default |

---

## Critical Implementation Patterns

### 1. Hybrid search — parallel Qdrant calls
```python
import asyncio

async def hybrid_search(question: str, filter_: dict, top_k: int):
    query_vector = await embed_query_text(question)
    sparse_vector = encode_sparse_text(question)

    dense_task = search_dense(collection, query_vector, filter_, top_k * 2)
    sparse_task = search_sparse(collection, sparse_vector, filter_, top_k * 2)

    dense_hits, sparse_hits = await asyncio.gather(dense_task, sparse_task)
    return dense_hits, sparse_hits
```

### 2. RRF merge
```python
def rrf_merge(dense_ids, sparse_ids, k=60) -> list[uuid.UUID]:
    scores: dict[uuid.UUID, float] = {}
    for rank, chunk_id in enumerate(dense_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    for rank, chunk_id in enumerate(sparse_ids, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: scores[x], reverse=True)
```

### 3. Cohere rerank
```python
import cohere

co = cohere.Client(settings.cohere_api_key)

def rerank(question: str, documents: list[str], top_n: int) -> list[int]:
    response = co.rerank(
        model="rerank-v3.5",
        query=question,
        documents=documents,
        top_n=top_n,
    )
    return [r.index for r in response.results]
```

### 4. Tenant filter builder
```python
def build_filter(tenant_id, project_id, scope_type=None, scope_id=None,
                 entity_id=None, snapshot_date=None, tags=None, acl=None):
    must = [
        {"key": "tenant_id", "match": {"value": str(tenant_id)}},
        {"key": "project_id", "match": {"value": str(project_id)}},
    ]
    if scope_type:
        must.append({"key": "scope_type", "match": {"value": scope_type}})
    if scope_id:
        must.append({"key": "scope_id", "match": {"value": scope_id}})
    # ... etc
    return {"must": must}
```

### 5. Redis conversation memory
```python
# app/services/chat.py
import json
from redis.asyncio import from_url

class RedisChatStore:
    def __init__(self, redis_url: str):
        self.client = from_url(redis_url)
        self.ttl = 1800  # 30 minutes
        self.max_turns = 6

    def _key(self, session_id: str) -> str:
        return f"chat:{session_id}"

    async def add_turn(self, session_id: str, role: str, content: str):
        key = self._key(session_id)
        await self.client.rpush(key, json.dumps({"role": role, "content": content}))
        await self.client.ltrim(key, -self.max_turns * 2, -1)  # keep last 6 turns (12 messages)
        await self.client.expire(key, self.ttl)

    async def get_history(self, session_id: str) -> list[dict]:
        key = self._key(session_id)
        raw = await self.client.lrange(key, 0, -1)
        return [json.loads(r) for r in raw]
```

### 6. Query service — session via Depends (NOT AsyncSessionLocal directly)
```python
# app/api/query.py
def _get_query_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> QueryService:
    service = getattr(request.app.state, "query_service", None)
    if service is not None:
        return service
    return QueryService(session)

# Endpoint:
@router.post("/query")
async def query(
    request: Request,
    payload: QueryRequest,
    service: QueryService = Depends(_get_query_service),
):
    ...
```
**Never** call `AsyncSessionLocal()` directly — session leak.

---

## Tasks

### Task 1 — Query Embedder
- [ ] `app/services/embedder.py` — `embed_query_text(text: str) -> list[float]`
  - Same model as ingestion: `gemini-embedding-2-preview`, `output_dimensionality=768`
  - Task type: `"retrieval_query"` (vs `"retrieval_document"` for ingestion)
  - Wrap sync Gemini SDK call in `asyncio.to_thread()`

**Test:** `tests/test_embedder.py` — monkeypatch `genai.embed_content`, check dimension

---

### Task 2 — Qdrant Search
- [ ] `app/services/vector_store.py` — add search methods
- [ ] `search_dense(collection, vector, filter_payload, limit) -> list[ScoredPoint]`
  ```json
  POST /collections/{name}/points/search
  {"vector": {"name": "dense", "vector": [...]}, "filter": {...}, "limit": N, "with_payload": true}
  ```
- [ ] `search_sparse(collection, sparse_vector, filter_payload, limit) -> list[ScoredPoint]`
  ```json
  POST /collections/{name}/points/search
  {"vector": {"name": "sparse", "vector": {"indices": [...], "values": [...]}}, "filter": {...}, "limit": N}
  ```
- [ ] `get_points_by_ids(collection, ids) -> list[Point]` — for parent chunk fetch
- [ ] Filter builder utility: tenant + project + optional scope/tags/acl/snapshot_date
- [ ] `ScoredPoint` dataclass: `id`, `score`, `payload`

**Test:** `tests/test_vector_store.py` — monkeypatch httpx, assert request body structure

---

### Task 3 — Sparse Encoder (query side)
- [ ] `app/services/sparse_encoder.py` — `encode_sparse_text(text: str) -> dict[int, float]`
  - Same function as ingestion side (shared)
  - Returns `{indices: list[int], values: list[float]}` for Qdrant sparse vector format

---

### Task 4 — Cohere Reranker
- [ ] `app/services/reranker.py` — `CohereRerankerService`
- [ ] `rerank(question, documents, top_n) -> list[int]` — returns reordered indices
  - Uses `cohere.Client(settings.cohere_api_key)`
  - Model: `"rerank-v3.5"`
  - If `cohere_api_key` empty: skip rerank, return original order
- [ ] Graceful fallback: if Cohere API fails, log warning, return original ranking

**Test:** `tests/test_reranker.py` — mock cohere client, assert index order

---

### Task 5 — Query Service
- [ ] `app/services/query.py` — `QueryService(session, vector_store, reranker)`
- [ ] `answer_question(question, project_id, *, retrieval_mode, scope_type, scope_id, entity_id, snapshot_date, tags, acl, collections, merge_strategy, exclude_sources, exclude_documents) -> dict`

  **Pipeline:**
  1. Load project config from DB (`top_k`, `threshold`, `latency_budget_ms`)
  2. Embed question → `query_vector`
  3. Encode sparse → `sparse_vector`
  4. `retrieval_mode`:
     - `"dense"` → search dense only
     - `"sparse"` → search sparse only
     - `"hybrid"` → both in parallel, RRF merge
  5. Filter by `exclude_sources`, `exclude_documents`
  6. Fetch parent chunk texts from DB (for context window expansion)
  7. Cohere rerank top-N candidates
  8. Build prompt with context + question
  9. Call LLM → answer text
  10. Return `{answer, retrieval_mode, retrieval_context, sources}`

- [ ] `_rrf_merge_hits(dense_hits, sparse_hits, k=60)` — RRF fusion
  - Remove dead code: check `sparse is None` → return dense, `dense is None` → return sparse, then fuse
- [ ] `_build_context(chunks) -> str` — concatenate parent + child text with separators
- [ ] `_call_llm(prompt: str) -> str` — agnostic; default Gemini Flash

**Test:** `tests/test_query_service.py` — mock vector_store + reranker, assert answer shape

---

### Task 6 — Chat Service
- [ ] `app/services/chat.py` — `ChatService(query_service, store)`
- [ ] `RedisChatStore` — `add_turn`, `get_history`, TTL 30min, trim to last 6 turns
- [ ] `create_default_chat_store()` — factory using `settings.redis_url`
- [ ] `ChatService.reply(message, project_id, session_id) -> dict`
  1. Load history from Redis
  2. Build contextual question: inject last 3 user messages as prefix
  3. Call `query_service.answer_question(contextual_question, ...)`
  4. Append user turn + assistant turn to Redis
  5. Return `{answer, session_id, retrieval_context, sources}`

**Test:** `tests/test_chat_service.py` — mock Redis store + query service, assert history append

---

### Task 7 — `/query` and `/chat` Endpoints
- [ ] `app/api/query.py`
- [ ] `POST /query` → `QueryResponse`
  - Accepts all retrieval filter fields from `QueryRequest`
  - Service via `Depends(_get_query_service)`
- [ ] `POST /chat` → `ChatResponse`
  - `session_id` auto-generated if not provided (uuid4)
  - Service via `Depends(_get_chat_service)` which chains `Depends(_get_query_service)`

**Critical:** Both `_get_query_service` and `_get_chat_service` MUST use `Depends(get_db_session)`:
```python
def _get_query_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> QueryService:
    service = getattr(request.app.state, "query_service", None)
    if service is not None:
        return service
    return QueryService(session)

def _get_chat_service(
    request: Request,
    query_service: QueryService = Depends(_get_query_service),
) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is not None:
        return service
    store = getattr(request.app.state, "chat_store", None) or create_default_chat_store()
    return ChatService(query_service, store)
```

**Test:** `tests/test_api_endpoints.py` — inject mock services via `app.state.*`

---

### Task 8 — Schemas
- [ ] `app/schemas/query.py`
  - `QueryRequest`: `question`, `retrieval_mode: "dense"|"sparse"|"hybrid"="hybrid"`, `scope_type?`, `scope_id?`, `entity_id?`, `snapshot_date?`, `tags?`, `acl?`, `collections?`, `merge_strategy: "rrf"="rrf"`, `exclude_sources?`, `exclude_documents?`
  - `RetrievalContext`: `title`, `snippet`, `parent_context`, `score`
  - `SourceItem`: `document_id`, `title`, `source_ref`, `snippet`, `score`
  - `QueryResponse`: `answer`, `retrieval_mode`, `retrieval_context: list[RetrievalContext]`, `sources: list[SourceItem]`
  - `ChatRequest`: `message`, `session_id?`
  - `ChatResponse`: `answer`, `session_id`, `retrieval_context?`, `sources?`

---

### Task 9 — LangGraph Self-RAG (Optional)
- [ ] `app/services/graph.py` — LangGraph `StateGraph`
- [ ] Nodes: `classify` → `retrieve` → `grade` → `rewrite` (if grade=no) → `generate` → `hallucination_check`
- [ ] Enable via `project.config["use_graph"] = true`
- [ ] `QueryService.answer_question` checks `use_graph` flag → routes to `graph.run()` or direct pipeline
- [ ] Langfuse `@observe` decorators on each node for tracing

**Note:** This is optional; implement only if `use_graph` feature is needed for a project.

---

## Verification

After all tasks complete:

```bash
# Ingest a document first (P2 prerequisite)
curl -X POST http://localhost:8000/ingest \
  -H "X-API-Key: test-key-1" \
  -H "X-Project-ID: <uuid>" \
  -d '{"source_type": "text", "source_ref": "Python is a programming language.", "mode": "sync"}'

# Query
curl -X POST http://localhost:8000/query \
  -H "X-API-Key: test-key-1" \
  -H "X-Project-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Python?", "retrieval_mode": "hybrid"}'

# Chat with session
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: test-key-1" \
  -H "X-Project-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is Python?", "session_id": "session-abc"}'

# Follow-up (history should be used)
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: test-key-1" \
  -H "X-Project-ID: <uuid>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Can you elaborate?", "session_id": "session-abc"}'
```

Expected: meaningful answer with `retrieval_context`, follow-up uses session history.
