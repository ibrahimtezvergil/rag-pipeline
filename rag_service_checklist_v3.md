# RAG Service — Checklist v3.0

**Strateji:** Önce kendi projeler (CRM, Sports App), sonra SaaS
**Stack:** FastAPI + PostgreSQL + Qdrant + Redis + ARQ + Langfuse
**Embedding:** Gemini Embedding 2 (multimodal — text, image, audio, video, PDF)

---

## Terminology Refactor Note — 2026-03-28

- Karar: domain dili `project` yerine `application` olarak refactor edilecek.
- Neden: mevcut ürün modelinde `tenant = şirket`, `application = CRM / Diet / Support instance`, `user = tenant içi kullanıcı`, `knowledge_scope = application içi alt veri alanı`. `project` adı bu modeli yanlış temsil ediyor ve `application` ile `scope` kavramlarını karıştırıyor.
- Planlanan refactor kapsamı: `rag_projects -> rag_applications`, `RagProject -> RagApplication`, `project_id -> application_id`, `X-Project-ID -> X-Application-ID`, cache/rate-limit/observability ve dokümantasyon yüzeyi.
- Geçiş stratejisi: dış API'de `X-Application-ID` ana header olacak; `X-Project-ID` kısa süreli deprecated fallback olarak kabul edilecek. İç kod ve DB modeli yalnızca `application` dili kullanacak.
- Spec: `docs/superpowers/specs/2026-03-28-application-domain-refactor-design.md`

---

## P1 — Core Altyapı (Servis çalışmadan önce tamamlanmalı)

### Proje İskeleti
- [x] FastAPI proje yapısı oluştur (`app/`, `workers/`, `tests/`) — Ref: `rag-service/app/main.py`, `rag-service/app/api/router.py` | Akış: `main -> router -> service/worker`
- [x] Docker Compose: FastAPI + PostgreSQL + Qdrant + Redis + Langfuse — Ref: `rag-service/docker-compose.yml` | Akış: `api + worker -> postgres/qdrant/redis/langfuse`
- [x] `.env` yapısı ve config yönetimi (`pydantic-settings`) — Ref: `rag-service/app/config.py` | Akış: `.env -> Settings -> app/services`
- [x] X-API-Key + X-Project-ID middleware (auth) — Ref: `rag-service/app/middleware/auth.py`, `rag-service/app/deps.py` | Akış: `header -> middleware -> request.state`
- [x] `/health` endpoint — Qdrant, PostgreSQL, Redis, Embedder durumu — Ref: `rag-service/app/api/health.py`, `rag-service/app/services/health.py` | Akış: `/health -> collector -> service checks`

### Veritabanı (PostgreSQL)
- [x] `rag_tenants` tablosu — Ref: `rag-service/app/models/db.py`, `rag-service/migrations/versions/001_initial_schema.py` | Akış: `tenant auth -> tenant row`
- [x] `rag_projects` tablosu — `config` JSONB dahil (top_k, threshold, latency_budget_ms, token_budget) — Ref: `rag-service/app/models/db.py` | Akış: `project header -> config -> retrieval/chat`
- [x] `rag_documents` tablosu — `version`, `previous_document_id`, `source_connector_id`, `file_size_bytes`, `title`, `embed_model` dahil — Ref: `rag-service/app/models/db.py` | Akış: `ingest request -> document row -> status/version`
- [x] `rag_chunks` tablosu — `parent_chunk_id`, `modality`, `page_number`, `bbox`, `section_title`, `acl`, `is_archived`, `embed_model`, `embed_version`, `dimension` dahil — Ref: `rag-service/app/models/db.py` | Akış: `chunker -> chunk rows -> qdrant bridge`
- [x] `rag_ingestion_jobs` tablosu — job_type, status, retry_count, duration_ms, chunks_processed — Ref: `rag-service/app/models/db.py`, `rag-service/workers/tasks/ingest.py` | Akış: `enqueue -> job row -> retry/status`
- [x] `rag_chunk_diff_log` tablosu — operation: new/modified/deleted/unchanged — Ref: `rag-service/app/models/db.py` | Akış: `ingest diff -> diff log row`
- [x] `rag_sync_checkpoints` tablosu — connector bazlı cursor_state — Ref: `rag-service/app/models/db.py` | Akış: `connector sync -> cursor_state`
- [x] `tenant_secrets` tablosu — BYOK için şema (implement etme, sadece tablo) — Ref: `rag-service/app/models/db.py` | Akış: `tenant -> provider secret ref`
- [x] Alembic migration yapısı — Ref: `rag-service/alembic.ini`, `rag-service/migrations/env.py` | Akış: `model change -> revision -> migrate`

### Ingestion Pipeline

#### Source Loaders
- [x] PDF loader — ≤6 sayfa: Gemini direct PDF path / >6 sayfa: pymupdf layout-aware chunking — Ref: `rag-service/app/services/loaders.py`, `rag-service/app/services/document_ai.py` | Akış: `PDF -> direct embed veya pymupdf chunk`
- [x] Structured loader — generic `records[]` → LLM semantic formatter → text embed (rule-based fallback) — Ref: `rag-service/app/services/summary_formatter.py`, `rag-service/app/services/ingestion.py` | Akış: `JSON -> semantic text -> embed`
- [x] Web loader — crawl4ai (JS render, nav/footer temizleme, static fallback) — Ref: `rag-service/app/services/loaders.py` | Akış: `URL -> crawl/render -> clean text -> chunk`
- [x] Audio loader — Gemini Embedding 2 native embed (120s clip window'lara böl) — Ref: `rag-service/app/services/media.py`, `rag-service/app/services/ingestion.py` | Akış: `audio -> 120s clips -> embed -> chunk rows`
- [ ] Video loader — ffmpeg → 120s clip → Gemini Embedding 2 (video modality)
- [ ] DB loader — SQL → SummaryFormatter → text embed — Ref: `rag-service/app/services/loaders.py`, `rag-service/app/services/summary_formatter.py` | Akış: `SQL result -> summary text -> embed` ⚠️ Devre dışı (2026-03-22): tenant izolasyonu yoktu — harici DB connection string + per-project scoping implement edilene kadar `NotImplementedError` fırlatıyor
- [x] Image loader — Gemini Embedding 2 direkt embed (PNG, JPEG) — Ref: `rag-service/app/services/loaders.py`, `rag-service/app/services/ingestion.py` | Akış: `image bytes -> direct embed -> vector row`
- [ ] Email loader — MIME parse → text embed
- [ ] Chat loader — WhatsApp / Slack export parse

#### Pipeline
- [x] SummaryFormatter — DB/JSON/tablo verisini natural language'a çevir (rule-based + structured LLM semantic path) — Ref: `rag-service/app/services/summary_formatter.py` | Akış: `structured input -> NL summary -> chunk/embed`
- [x] Source-aware chunker — pdf/web stratejileri — Ref: `rag-service/app/services/chunking.py` | Akış: `source type -> chunk strategy -> chunk list`
- [x] Parent-child chunk oluşturma — `parent_chunk_id` FK ile — Ref: `rag-service/app/services/ingestion.py`, `rag-service/app/repositories/ingestion.py` | Akış: `parent row -> child rows -> FK resolve`
- [x] Chunk kalite filtresi (text) — boş/duplicate atla, min/max split uygula — Ref: `rag-service/app/services/chunking.py` | Akış: `raw text -> normalize/filter -> split`
- [x] `bbox` ve `page_number` PDF chunk'larına eklenmesi (pymupdf path) — Ref: `rag-service/app/services/document_ai.py`, `rag-service/app/services/ingestion.py` | Akış: `layout parse -> bbox/page -> chunk metadata`
- [x] Content hash (SHA256) — document ve chunk seviyesi — Ref: `rag-service/app/services/ingestion.py` | Akış: `content -> sha256 -> dedup/version refs`
- [x] Büyük dosya: URL pipeline (Hetzner Object Storage → Python indir) — Ref: `rag-service/app/services/loaders.py` | Akış: `remote url -> download -> ingest`
- [x] Büyük dosya: Base64 pipeline (≤50MB) — Ref: `rag-service/app/schemas/ingest.py`, `rag-service/app/services/ingestion.py` | Akış: `base64 payload -> bytes -> loader`

### Embedding (Gemini Embedding 2)
- [x] `gemini-embedding-2` entegrasyonu — multimodal API çağrısı — Ref: `rag-service/app/services/embedder.py` | Akış: `content -> Gemini embed -> vector`
- [x] `task_type`: RETRIEVAL_DOCUMENT (index) / RETRIEVAL_QUERY (query) — Ref: `rag-service/app/services/embedder.py`, `rag-service/app/services/query.py` | Akış: `index/query intent -> proper task_type`
- [x] MRL dimension ayarı — 768 (default 3072'den truncate) — Ref: `rag-service/app/services/embedder.py`, `rag-service/app/services/vector_store.py` | Akış: `3072 -> truncate 768 -> qdrant`
- [x] Embedding versioning — `embed_model`, `embed_version`, `dimension` kolonu — Ref: `rag-service/app/models/db.py`, `rag-service/app/services/ingestion.py` | Akış: `embed result -> row metadata`
- [x] Rate limit handler + retry (exponential backoff) — Ref: `rag-service/app/services/embedder.py` | Akış: `embed call -> backoff -> retry/fail`

### Vector Store (Qdrant)
- [x] Collection oluşturma — 768 dim, sabit — Ref: `rag-service/app/services/vector_store.py`, `rag-service/app/services/collections.py` | Akış: `create collection -> named vectors ready`
- [x] Chunk upsert — payload: tenant_id, scope_type, scope_id, source_type, modality, acl — Ref: `rag-service/app/services/vector_store.py` | Akış: `chunk row -> payload/vector -> qdrant upsert`
- [x] Qdrant ↔ PostgreSQL köprüsü — `qdrant_point_id` — Ref: `rag-service/app/models/db.py`, `rag-service/app/services/ingestion.py` | Akış: `qdrant point -> chunk row bridge`
- [x] Soft-delete — `is_archived=True` + Qdrant'tan sil — Ref: `rag-service/app/api/ingest.py`, `rag-service/app/services/ingestion.py`, `rag-service/app/services/vector_store.py` | Akış: `delete -> archive row -> qdrant delete`

### Queue (ARQ + Redis)
- [x] ARQ worker yapısı — pdf/web için gerçek async IO worker — Ref: `rag-service/workers/tasks/ingest.py` | Akış: `redis queue -> arq worker -> ingestion service`
- [x] `VectorIngestJob` — pdf/web için load → chunk → embed → upsert — Ref: `rag-service/workers/tasks/ingest.py`, `rag-service/app/services/ingestion.py` | Akış: `job -> load -> chunk -> embed -> qdrant/db`
- [x] Failed job retry (max 3, exponential backoff) — `rag_ingestion_jobs` tablosuna yaz — Ref: `rag-service/workers/tasks/ingest.py`, `rag-service/app/models/db.py` | Akış: `failure -> retry/backoff -> job status`
- [x] Sync/Async mod — `/ingest?mode=sync|async` — Ref: `rag-service/app/api/ingest.py` | Akış: `/ingest -> direct run veya queue`

### API Endpoints
- [x] `POST /ingest` — async, document_id döner — Ref: `rag-service/app/api/ingest.py` | Akış: `request -> ingest service/queue -> document_id`
- [x] `POST /ingest/batch` — toplu doküman kuyruğa al — Ref: `rag-service/app/api/ingest.py` | Akış: `batch request -> enqueue many jobs`
- [x] `GET /ingest/{id}` — status: pending/indexing/indexed/failed — Ref: `rag-service/app/api/ingest.py`, `rag-service/app/repositories/ingestion.py` | Akış: `id -> job/document lookup -> status`
- [x] `DELETE /ingest/{id}` — doküman + chunk sil (soft-delete) — Ref: `rag-service/app/api/ingest.py`, `rag-service/app/services/ingestion.py` | Akış: `delete -> archive/delete vectors`
- [x] `POST /query` — tek seferlik soru-cevap — Ref: `rag-service/app/api/query.py`, `rag-service/app/services/query.py` | Akış: `question -> retrieve -> rerank -> answer`
- [x] `POST /chat` — conversation (Redis session ile) — Ref: `rag-service/app/api/query.py`, `rag-service/app/services/chat.py` | Akış: `chat turn -> memory -> query service`
- [x] `GET /collections` — collection listesi — Ref: `rag-service/app/api/collections.py`, `rag-service/app/services/collections.py` | Akış: `request -> qdrant collections`
- [x] `POST /collections` — yeni collection — Ref: `rag-service/app/api/collections.py`, `rag-service/app/services/collections.py` | Akış: `request -> vector store create`
- [x] `GET /health` — Ref: `rag-service/app/api/health.py` | Akış: `request -> service probes -> status`

---

## P2 — Query Pipeline & Gelişmiş Özellikler

### Retrieval
- [x] Dense search — Gemini Embedding 2 → Qdrant — Ref: `rag-service/app/services/query.py`, `rag-service/app/services/vector_store.py` | Akış: `query embed -> qdrant dense search`
- [x] Sparse search — BM25 (Snowball Türkçe stemmer) → Qdrant — Ref: `rag-service/app/services/sparse_encoder.py`, `rag-service/app/services/vector_store.py` | Akış: `text -> sparse vector -> qdrant sparse search`
- [x] RRF fusion — dense + sparse birleştir — Ref: `rag-service/app/services/query.py` | Akış: `dense hits + sparse hits -> RRF merge`
- [x] Cohere Rerank-3 entegrasyonu — Ref: `rag-service/app/services/reranker.py`, `rag-service/app/services/query.py` | Akış: `hybrid candidates -> Cohere rerank -> final order`
- [x] Dinamik top-K ve score threshold — senaryo bazlı config — Ref: `rag-service/app/services/query.py`, `rag-service/app/models/db.py` | Akış: `project config -> candidate cut/filter`
- [x] Multi-collection query — `collections[]` + `merge_strategy` — Ref: `rag-service/app/schemas/query.py`, `rag-service/app/services/query.py` | Akış: `collections[] -> per collection retrieve -> merge`
- [x] Negative filtering — `exclude_sources`, `exclude_documents` — Ref: `rag-service/app/schemas/query.py`, `rag-service/app/services/query.py` | Akış: `request excludes -> source prune`
- [x] Chunk seviyesi ACL — `acl[]` payload filter — Ref: `rag-service/app/schemas/ingest.py`, `rag-service/app/services/vector_store.py`, `rag-service/app/services/query.py` | Akış: `ingest acl -> qdrant filter -> post-filter`
- [x] Parent-child resolution — child bul → parent getir — Ref: `rag-service/app/services/query.py`, `rag-service/app/repositories/ingestion.py` | Akış: `child hit -> parent context resolve`

### LangGraph Pipeline
- [x] Direkt pipeline (basit soru-cevap) — Ref: `rag-service/app/services/query.py`, `rag-service/app/services/prompts.py`, `rag-service/app/services/llm.py` | Akış: `retrieve -> rerank -> prompt build -> LLM generate -> fallback on error`
- [ ] LangGraph Self-RAG akışı — classify → retrieve → grade → rewrite → generate → hallucination_check
- [x] Latency budget enforcement — `latency_budget_ms` aşınca early abort — Ref: `rag-service/app/services/query.py`, `rag-service/tests/test_query_service.py` | Akış: `query start -> retrieval/rerank elapsed -> remaining budget hesapla -> düşükse LLM skip -> _fallback_answer`
- [x] Token budget enforcement — `token_budget` aşınca generate kısalt — Ref: `rag-service/app/services/query.py`, `rag-service/tests/test_query_service.py` | Akış: `final sources -> approx token hesabı -> source/context trim -> prompt build`
- [ ] Config toggle — `use_graph: true/false`

### Langfuse Entegrasyonu
- [x] Langfuse Docker Compose'a ekle (self-host) — Ref: `rag-service/docker-compose.yml` | Akış: `compose up -> langfuse_db + langfuse ayrı kalkar, app DB ile migration çakışmaz`
- [x] FastAPI pipeline'larına `@observe` decorator — Ref: `rag-service/app/services/tracing.py`, `rag-service/app/api/query.py`, `rag-service/app/api/ingest.py`, `rag-service/app/services/query.py`, `rag-service/app/services/ingestion.py`, `rag-service/app/services/llm.py`, `rag-service/app/services/embedder.py`, `rag-service/app/services/reranker.py` | Akış: `heavy endpoint -> root observe -> safe metadata update -> query/ingest/provider child spans -> fail-open tracing`
- [ ] LangGraph node'larına trace/span ekleme
- [ ] Maliyet ve latency dashboard kurulumu

### Conversation Memory
- [x] Redis session yönetimi — `POST /chat` session_id döner — Ref: `rag-service/app/services/chat.py` | Akış: `session_id -> RedisChatStore -> history`
- [x] Son 6 tur sakla, TTL 30 dakika — Ref: `rag-service/app/services/chat.py` | Akış: `turn append -> trim to 6 -> TTL 30min`
- [x] Takip sorusunda history otomatik inject — Ref: `rag-service/app/services/chat.py` | Akış: `history load -> inject prompt -> query service`

### Caching
- [x] Query cache — `sha256(query + tenant_id + scope_id)` → Redis TTL 1 saat — Ref: `rag-service/app/services/query_cache.py`, `rag-service/app/services/query.py` | Akış: `request fingerprint -> Redis get -> cache hit return / miss run pipeline -> JSON store (TTL 1h)`
- [x] Cache invalidation — collection re-index edilince — Ref: `rag-service/app/services/query_cache.py`, `rag-service/app/services/ingestion.py` | Akış: `successful ingest/delete -> project cache index lookup -> cached query keys delete`

### Re-index & Versioning
- [x] Document versioning — `version++`, `previous_document_id` — Ref: `rag-service/app/repositories/ingestion.py`, `rag-service/app/services/ingestion.py` | Akış: `same project+source_ref ingest -> latest version lookup -> new document version++ -> successful index sonrası previous version supersede/archive`
- [x] Chunk-level hash karşılaştırma — sadece değişen chunk'lar embed edilir — Ref: `rag-service/app/services/ingestion.py`, `rag-service/app/services/vector_store.py` | Akış: `previous child hashes + qdrant vector fetch -> unchanged chunk vector reuse -> only changed chunks re-embed`
- [x] Diff log yazımı — `rag_chunk_diff_log` her ingestion'da doldur — Ref: `rag-service/app/repositories/ingestion.py`, `rag-service/app/services/ingestion.py` | Akış: `ingest compare -> new/modified/unchanged/deleted classification -> rag_chunk_diff_log rows`
- [x] Scheduled re-index — `POST /schedules`, cron bazlı ARQ job — Ref: `rag-service/app/api/schedules.py`, `rag-service/app/services/schedules.py`, `rag-service/workers/tasks/schedules.py` | Akış: `POST /schedules -> rag_schedules persist(next_run_at) -> ARQ cron tick due schedule scan -> checkpoint merge -> async ingestion enqueue`
- [x] `rag_sync_checkpoints` — connector bazlı cursor_state güncelleme — Ref: `rag-service/app/repositories/ingestion.py`, `rag-service/app/services/ingestion.py` | Akış: `ingest payload source_connector_id/cursor_state -> document metadata -> successful indexing sonrası checkpoint upsert(last_synced_at, cursor_state)`

### Observability
- [x] Structured JSON log — ingestion (chunk_indexed, modality, embed_ms, token_count) — Ref: `rag-service/app/services/observability.py`, `rag-service/app/services/ingestion.py` | Akış: `chunk indexed -> event payload -> logger.info(json)`
- [x] Structured JSON log — query (query_hash, reranker_ms, llm_ms, top_chunk_score) — Ref: `rag-service/app/services/observability.py`, `rag-service/app/services/query.py` | Akış: `query finish -> metrics/hash -> logger.info(json)`
- [x] Query içeriği loglanmaz — sadece SHA256 hash (GDPR) — Ref: `rag-service/app/services/observability.py`, `rag-service/app/services/query.py` | Akış: `question -> sha256(tenant+project scoped) -> log payload`
- [x] Embedding versioning — stale chunk tespiti, ARQ kuyruğuna al — Ref: `rag-service/app/services/ingestion.py`, `rag-service/app/repositories/ingestion.py`, `rag-service/workers/tasks/ingest.py` | Akış: `latest indexed docs -> child chunk embed_version compare -> stale doc detect -> async ingestion requeue -> hourly ARQ scan`

### Diğer
- [x] Audio metadata pipeline (opsiyonel) — Whisper + pyannote diarization (timestamp + speaker metadata için) — Ref: `rag-service/app/services/audio_metadata.py`, `rag-service/app/services/ingestion.py`, `rag-service/tests/test_audio_metadata.py`, `rag-service/tests/test_worker_ingest.py` | Akış: `audio bytes -> best-effort metadata extract -> transcript/segments document metadata -> clip transcript varsa audio chunk content enrich, yoksa clip summary fallback`
- [x] Ingestion webhook callback — HMAC-SHA256 imzalı, `callback_url` desteği — Ref: `rag-service/app/services/callbacks.py`, `rag-service/app/schemas/ingest.py`, `rag-service/app/services/ingestion.py`, `rag-service/workers/tasks/ingest.py`, `rag-service/tests/test_callbacks.py`, `rag-service/tests/test_worker_ingest.py` | Akış: `async ingest request -> callback_url enqueue payload -> worker completed/failed -> signed POST -> fail-open callback delivery`
- [x] Rate limiting — Redis sliding window, project_id bazlı, 429 + Retry-After — Ref: `rag-service/app/services/rate_limit.py`, `rag-service/app/deps.py`, `rag-service/app/api/query.py`, `rag-service/app/api/ingest.py` | Akış: `project+route -> redis sliding window -> 429/Retry-After`
- [x] Circuit breaker — Qdrant/Gemini/Cohere/LLM per-service kurallar — Ref: `rag-service/app/services/circuit_breaker.py`, `rag-service/app/services/llm.py`, `rag-service/app/services/embedder.py`, `rag-service/app/services/reranker.py`, `rag-service/app/services/vector_store.py`, `rag-service/app/services/query.py` | Akış: `provider boundary -> before_call -> upstream call -> success/failure state update -> fast-fail veya mevcut query fallback`
- [x] Confidence score — top chunk score ortalaması, düşükse uyarı — Ref: `rag-service/app/services/query.py`, `rag-service/app/schemas/query.py` | Akış: `final source scores -> normalize -> average -> confidence_score + optional warning`
- [x] Query expansion — sinonim sözlüğü + LLM genişletme — Ref: `rag-service/app/services/query_expansion.py`, `rag-service/app/services/query.py` | Akış: `question -> synonym expand -> optional llm rewrite -> retrieval input`

---

## P3 — Production Olgunlaşma

### Veri Kalitesi
- [x] Semantic deduplication — embedding similarity > 0.97 ise atla — Ref: `rag-service/app/services/ingestion.py`, `rag-service/app/services/vector_store.py`, `rag-service/app/config.py` | Akış: `text child embed -> qdrant nearest-neighbor duplicate check -> score>=0.97 ise chunk skip -> diğer chunklar normal upsert`
- [x] Adaptive chunking — içerik yoğunluğuna göre otomatik chunk size — Ref: `rag-service/app/services/chunking.py` | Akış: `raw chunk normalize -> punctuation/list/cümle yoğunluğu heuristiği -> adaptive max_tokens -> split`
- [x] RAG Evaluation Pipeline — faithfulness, answer_relevancy, context_recall — Ref: `rag-service/app/api/evaluations.py`, `rag-service/app/services/evaluations.py`, `rag-service/app/repositories/evaluations.py`, `rag-service/workers/tasks/evaluations.py` | Akış: `POST /evaluations -> rag_evaluation_runs/samples persist -> ARQ run_evaluation_job -> mevcut query pipeline her sample için çalışır -> skorlar sample/run seviyesinde DB'ye yazılır -> GET /evaluations/{id}`
- [x] Feedback loop — `POST /feedback` (rating, chunk_ids) → kötü chunk'ları düşür — Ref: `rag-service/app/api/feedback.py`, `rag-service/app/services/feedback.py`, `rag-service/app/repositories/feedback.py`, `rag-service/app/services/query.py` | Akış: `query response source.chunk_id -> POST /feedback kaydi -> rag_chunk_feedback persist -> sonraki query final source listesinde negatif feedback alan chunk score penalty alir`

### Ölçek
- [x] Qdrant post-filtering fetch — sadece ID+metadata Qdrant'ta, metin PostgreSQL'den — Ref: `rag-service/app/services/vector_store.py`, `rag-service/app/services/query.py`, `rag-service/app/repositories/ingestion.py` | Akış: `qdrant returns chunk_id/document_id/score -> query service DB chunk fetch -> snippet/parent_context postgres chunk content`
- [ ] PostgreSQL partition stratejisi — tiered: shared (<100K chunk), dedicated (≥100K)
- [x] PgBouncer — transaction pool_mode, 20-50 pool size — Ref: `rag-service/docker-compose.yml`, `rag-service/app/db/session.py`, `rag-service/migrations/env.py`, `rag-service/docker/pgbouncer/Dockerfile` | Akış: `api/worker -> pgbouncer:6432 transaction pool -> postgres`, `runtime URL prepared_statement_cache_size=0 + NullPool`, `alembic -> DATABASE_DIRECT_URL`, `container non-root çalışır`
- [x] Document relationship — `related_chunks` metadata, bölümler arası referans — Ref: `rag-service/app/services/ingestion.py`, `rag-service/app/repositories/ingestion.py`, `rag-service/app/services/query.py`, `rag-service/app/models/db.py` | Akış: `ingest child chunklar icin sibling/section heuristigi -> related_chunk_ids persist -> query source output related_chunks metadata olarak yakin bolumleri dondurur`

### Admin & Yönetim
- [ ] Filament admin panel — tenant listesi, API key yönetimi
- [ ] Usage dashboard — proje bazlı token/query maliyet raporu
- [ ] Laravel SDK — HTTP wrapper, her projede tekrar yazma
- [x] Staging ortamı — ayrı Qdrant + PostgreSQL instance — Ref: `rag-service/docker-compose.staging.yml`, `rag-service/.env.staging.example`, `docs/operations/rag-service-staging-runbook.md`, `rag-service/tests/test_deployment_config.py` | Akış: `staging compose -> isolated postgres/qdrant/redis/langfuse -> env.staging config -> migrate -> health/ingest/query smoke runbook`

---

## P4 — SaaS

### Kullanıcı & Ödeme
- [ ] Self-serve kayıt — email + şifre, API key otomatik üretimi
- [ ] Plan limitleri — Free tier, hard limit enforcement
- [ ] Stripe entegrasyonu — Starter / Growth plan ödemesi
- [ ] BYOK implement — tenant kendi Gemini/OpenAI anahtarını girebilir
- [ ] Email bildirimleri — limit uyarısı, ingestion hatası

### Özellikler
- [ ] Streaming response — FastAPI SSE, `/query?stream=true`
- [ ] Multimodal query — görsel ile sorgulama (Gemini Embedding 2 native)
- [ ] Hot/cold storage — eski chunk'ları Qdrant'tan arşivle, on-demand re-index
- [ ] PII maskeleme — Microsoft Presidio, TC Kimlik/IBAN/telefon redaction
- [ ] n8n / Make.com / Zapier node

### Dokümanlar & Destek
- [ ] Public docs — docs sitesi, quick start rehberi
- [ ] SSO/SAML — Business plan
- [ ] Enterprise self-host seçeneği
- [ ] Retrieval quality analytics — hangi chunk kaç kere döndü, ortalama skor
- [ ] Vertical landing pages — Legal, E-commerce, Call Center

---

## Kararlar Özeti

| Konu | Karar |
|---|---|
| Registry | PostgreSQL (Docker) — başından beri |
| Embedding | `gemini-embedding-2` — tek model, tüm modalities |
| Embedding dim | 768 (MRL truncated, default 3072'den) |
| Audio embed | Gemini Embedding 2 native (Whisper = opsiyonel, metadata için) |
| Image embed | Gemini Embedding 2 direkt (Vision API yok) |
| Video embed | ffmpeg → 120s clip → Gemini Embedding 2 |
| PDF embed | ≤6 sayfa direkt / >6 sayfa pymupdf + chunking |
| Text context | 8192 token |
| Worker | CPU pool (video ffmpeg) + IO pool (embed, web, DB) |
| LLM | Agnostic — openai/anthropic/gemini/ollama provider abstraction |
| Observability | Structured JSON log + Langfuse (self-host) |
| Deployment | Docker Compose, Nginx, Hetzner, Dokploy |

---

## Code Review Sonuçları — 2026-03-22

### Genel Değerlendirme

P1 ve P2 kapsamındaki tüm [x] işaretli maddeler büyük ölçüde gerçek, çalışır kod olarak implement edilmiştir. Auth middleware JSONResponse kullanıyor (HTTPException değil), embedding model adı ve 768 boyutu tutarlı, parent-child chunk modeli FK ile doğru kurulmuş, hybrid RRF+Rerank akışı çalışır halde. 2 kritik bug, 3 önemli sorun, 1 yanlış [x] işaretlenmiş madde ve P2'de yanlış [ ] bırakılmış 3 madde tespit edilmiştir.

---

### ✅ Doğrulanan Maddeler

- **FastAPI proje yapısı:** `main.py`, `api/router.py`, tüm alt routerlar doğru. `create_app()` factory pattern, middleware ve router kayıtları yerinde.
- **Docker Compose:** FastAPI + PostgreSQL + Qdrant + Redis + Langfuse servisleri tanımlı; healthcheck ve `depends_on` doğru.
- **Config yönetimi (pydantic-settings):** `Settings` sınıfı `pydantic_settings.BaseSettings` kullanıyor, `.env` okunuyor, `api_keys_set` property doğru.
- **X-API-Key + X-Project-ID middleware:** `AuthMiddleware` JSONResponse (HTTPException değil) döndürüyor — spec ile tam uyumlu. `request.state.api_key` ve `request.state.project_id` setleniyor.
- **`/health` endpoint:** Qdrant, PostgreSQL, Redis, Embedder probe'ları çalışıyor; degraded durumda 503 dönüyor.
- **Tüm veritabanı tabloları:** `db.py` modeli ve `001_initial_schema.py` migration tam uyumlu — tüm 8 tablo mevcut.
- **`rag_chunks` kolonları:** `parent_chunk_id`, `modality`, `page_number`, `bbox`, `section_title`, `acl`, `is_archived`, `embed_model`, `embed_version`, `dimension` hepsi mevcut.
- **Alembic migration yapısı:** `env.py` `asyncpg` prefix'ini temizleyerek sync engine kullanıyor — doğru yaklaşım.
- **PDF loader:** ≤6 sayfa Gemini direct (`document_ai.py`), >6 sayfa pymupdf layout chunking (`loaders.py`). Her iki strateji çalışıyor.
- **Structured loader:** `format_structured_data_semantically` Gemini Flash ile LLM semantic path, API key yoksa rule-based fallback.
- **Web loader:** crawl4ai primary, static HTML fallback, JSON content fallback. Nav/footer strip edilmiş.
- **DB loader:** ~~SELECT/WITH whitelist regex kontrolü var. `format_structured_data` ile text dönüşümü yapılıyor.~~ ⚠️ Sonradan devre dışı bırakıldı (2026-03-22): `load_db_source` tenant izolasyonu olmadan internal engine'e erişiyordu. Şu an `NotImplementedError` fırlatıyor — bkz. Düzeltme Notu §Kritik #2.
- **Image loader:** `load_image_source` + `embed_image_content` + MIME detection çalışıyor. Parent+child chunk pattern ile Qdrant'a kaydediliyor.
- **SummaryFormatter:** Rule-based + LLM semantic path, email/telefon redaction, input/output char limit truncation — tam implement.
- **Source-aware chunker:** `build_chunks` pdf ve text strategy ayırt ediyor. `_filter_and_split` ile duplicate/min-token filtreleme.
- **Parent-child chunk:** `__PARENT_INDEX__:N` sentinel pattern ile repository `create_chunks` FK'yi resolve ediyor.
- **Chunk kalite filtresi:** Boş ve duplicate chunk'lar atlanıyor, min/max token split uygulanıyor.
- **bbox ve page_number:** pymupdf path'te `_merge_bboxes` ile chunk'lara ekleniyor.
- **Content hash (SHA256):** Hem document hem chunk seviyesinde `hashlib.sha256` kullanıyor.
- **Büyük dosya URL pipeline:** `load_binary_source` ile httpx download.
- **Büyük dosya Base64 pipeline:** `decode_base64_source` `validate=True` ile güvenli decode.
- **Gemini embedding entegrasyonu:** `_embed_parts` ile multimodal API çağrısı, `outputDimensionality: 768`, `taskType` parametresi doğru.
- **task_type RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY:** `embed_query_text` RETRIEVAL_QUERY, diğer fonksiyonlar RETRIEVAL_DOCUMENT kullanıyor.
- **MRL dimension 768:** `outputDimensionality: settings.embed_dimension` (768) embed çağrılarında gönderiliyor.
- **Embedding versioning:** `embed_model`, `embed_version`, `dimension` chunk row'a yazılıyor.
- **Rate limit + retry (exponential backoff):** `_post_with_retry` 429 durumunda [1, 2, 4] saniyelik backoff uyguluyor.
- **Qdrant collection oluşturma:** `ensure_collection` dense (768 dim, Cosine) + sparse vector alanı tanımlıyor.
- **Chunk upsert payload:** `tenant_id`, `scope_type`, `scope_id`, `source_type`, `modality`, `acl` payload'a ekleniyor.
- **Qdrant-PostgreSQL köprüsü:** `qdrant_point_id` UUID olarak chunk'a yazılıyor.
- **Soft-delete:** `soft_delete_document` + `archive_chunks` + `delete_points` zincirleme çalışıyor.
- **ARQ worker yapısı:** `WorkerSettings`, `run_ingest_job`, `func(run_ingest_job, max_tries=3)` doğru tanımlanmış.
- **Failed job retry (max 3, exponential backoff):** `Retry(defer=2**(job_try-1))`. `record_retry` / `record_failure` DB'ye yazılıyor.
- **Sync/Async mod:** `?mode=sync|async` query param, sync'te direkt işlem, async'te `dispatcher.enqueue`.
- **Tüm API endpointleri** (POST /ingest, /ingest/batch, GET /ingest/{id}, DELETE /ingest/{id}, POST /query, POST /chat, GET /collections, POST /collections, GET /health): Doğru HTTP status kodları ile çalışıyor.
- **Dense search:** `embed_query_text` + `search_chunks` (using: dense) akışı.
- **Sparse search:** `encode_sparse_text` blake2b hashing ile term frequency sparse vector, `search_sparse_chunks` (using: sparse).
- **RRF fusion:** `_rrf_merge_hits` dense + sparse chunk skorlarını RRF formülüyle (1/(k+rank)) birleştiriyor.
- **Cohere Rerank-3 entegrasyonu:** `CohereRerankerService` `/v2/rerank` endpoint kullanıyor, cohere_api_key yoksa atlıyor.
- **Dinamik top-K ve score threshold:** `_resolve_retrieval_config` project.config'den override alıyor.
- **Multi-collection query:** `collections[]` parametresi per-collection store oluşturuyor, `_merge_collection_hit_sets` ile birleştiriyor.
- **Negative filtering:** `_apply_negative_filters` `exclude_sources` ve `exclude_documents` ile çalışıyor.
- **Chunk seviyesi ACL:** Qdrant payload'da `acl` alanı, `should` filter ile sorgulanıyor, `_apply_acl_filter` ile post-filter.
- **Parent-child resolution:** `_build_sources` child chunk'ın `parent_chunk_id`'sini çekip `parent_context` alanına dolduruyor.
- **Langfuse Docker Compose:** `langfuse/langfuse:2` image mevcut.
- **Test coverage:** auth, health, api_endpoints, vector_store, query_service, worker_ingest, sparse_encoder, reranker testleri anlamlı ve çalışıyor.

---

### ⚠️ Sorunlu Maddeler

- **Session lifecycle — `_get_ingestion_service` ve `_get_query_service`** `app/api/ingest.py:32`, `app/api/query.py:24`
  - **Sorun:** `AsyncSessionLocal()` doğrudan çağrılıyor ama `async with` bloğu olmadan — session hiçbir zaman `close()` edilmiyor. Her `/ingest` ve `/query` çağrısında connection pool'dan connection sızdırılıyor.
  - **Önem:** Kritik
  - **Düzeltme:** `_get_ingestion_service` / `_get_query_service` kaldırılıp `Depends(get_db_session)` dependency injection ile session yönetimi yapılmalı.

- **DB loader çok-kiracılı izolasyon eksikliği** `app/services/loaders.py:243`
  - **Sorun:** `load_db_source` RAG servisinin kendi application veritabanı engine'ini kullanıyor (`from app.db.session import engine`). Tenant izolasyonu yok — bir tenant başkasının `rag_documents`, `rag_chunks` tablolarını okuyabilir. DB loader'ın hedefi de belirsiz: RAG'ın kendi DB'si mi yoksa müşteri verisi olan harici DB mi?
  - **Önem:** Kritik (güvenlik / çok-kiracılı izolasyon)
  - **Düzeltme:** Loader'ın amacı netleştirilmeli. Internal DB hedefliyorsa en azından `tenant_id` row-level filter zorunlu. Harici DB hedefliyorsa ayrı connection string alınmalı, internal engine kullanılmamalı.

- **`collect_health_status` sırayla await** `app/services/health.py:55-61`
  - **Sorun:** 4 servis check'i sırayla `await` ediliyor. Bir servis down veya yavaş olursa `/health` response süresi uzuyor (worst case 4×timeout = 20 saniye).
  - **Önem:** Önemli
  - **Düzeltme:** `asyncio.gather(check_postgres(), check_redis(), check_qdrant(), check_embedder())` ile paralel çağrı.

- **`CollectionsService.create_collection` sparse vector tanımlamaması** `app/services/collections.py:41-50`
  - **Sorun:** `POST /collections` ile oluşturulan collection'larda sadece dense vector var; `"sparse_vectors": {"sparse": {}}` eksik. `QdrantVectorStore.ensure_collection` sparse tanımlıyor ama `CollectionsService.create_collection` tanımlamıyor. Bu collection'lara sparse search yapıldığında Qdrant hata verir.
  - **Önem:** Önemli
  - **Düzeltme:** `create_collection` payload'una `"sparse_vectors": {"sparse": {}}` eklenmeli.

- **Embed model adı tutarsızlığı** `app/config.py:18`
  - **Sorun:** Checklist ve spec'te `gemini-embedding-2-preview` yazıyor ancak `config.py`'de default `"gemini-embedding-2"` (preview suffix yok). Yanlış model adı API çağrısının başarısız olmasına yol açabilir.
  - **Önem:** Önemli
  - **Düzeltme:** Gemini API'sinin mevcut model adı doğrulanıp `.env.example` ve `config.py` default'u güncellenmeli.

- **`_rrf_merge_hits` erişilemeyen kod** `app/services/query.py:296-297`
  - **Sorun:** `sparse_document_ids is None and dense_document_ids is None` koşulu hiçbir zaman çalışmıyor — her iki None durumu önceki dallarda zaten ele alınmış.
  - **Önem:** Küçük
  - **Düzeltme:** Erişilemeyen kontrol kaldırılabilir veya koşul sıralaması düzeltilmeli.

---

### ❌ Yanlış İşaretlenmiş [x] Maddeler (implement edilmemiş)

- **[x] Audio loader — Gemini Embedding 2 native embed (120s clip window'lara böl):** `app/services/media.py` sadece generic binary loader ve MIME detection içeriyor. `load_source` fonksiyonunda `audio` source_type case'i yok. `IngestionService._build_chunk_rows`'da audio modality için özel bir dal içermiyor. 120 saniye clip bölme ve audio'ya özgü embed çağrısı implement edilmemiş. Bu madde `[ ]` olarak işaretlenmeli.

---

### 🔄 Yanlış [ ] Bırakılmış Maddeler (implement var)

> ✅ Bu bölüm uygulandı — 3 madde checklist'te `[x]` olarak güncellendi (bkz. Düzeltme Notu §Checklist Güncellemeleri).

~~P2 "Conversation Memory" bölümündeki aşağıdaki 3 madde `[ ]` olarak işaretli, ancak `app/services/chat.py`'de tam olarak implement edilmiş:~~
- ~~`[ ]` Redis session yönetimi → `RedisChatStore` ile tam implement~~
- ~~`[ ]` Son 6 tur sakla, TTL 30 dakika → `ltrim(-6, -1)`, TTL=1800s~~
- ~~`[ ]` Takip sorusunda history otomatik inject → `_build_contextual_question`~~

---

### 📊 Özet Tablo

| Kategori | Sayı |
|---|---|
| Doğrulanan [x] madde | 48 |
| Sorunlu (Kritik) | 2 |
| Sorunlu (Önemli) | 3 |
| Sorunlu (Küçük) | 1 |
| Yanlış [x] işaretlenmiş (impl eksik) | 1 |
| Yanlış [ ] bırakılmış (impl var) | 3 |

---

## Düzeltme Notu — 2026-03-22

Review bulgularının tamamı kod üzerinde uygulandı. Unit testler geçiyor (104 unit test; integration testler DB bağlantısı gerektirdiğinden yalnızca `127.0.0.1:55432` ayakta olduğunda çalışır).

### ✅ Uygulanan Düzeltmeler

**Kritik #1 — Session leak** (`app/api/ingest.py`, `app/api/query.py`)
- `AsyncSessionLocal()` bare çağrısı kaldırıldı
- `_get_ingestion_service` ve `_get_query_service` artık `session: AsyncSession = Depends(get_db_session)` alıyor
- Tüm endpoint'ler service'i `Depends(...)` üzerinden alıyor — FastAPI session lifecycle'ı yönetiyor
- `_get_chat_service` de `Depends(_get_query_service)` zinciriyle düzeltildi

**Kritik #2 — DB loader cross-tenant erişim** (`app/services/loaders.py`)
- `load_db_source` devre dışı bırakıldı — `NotImplementedError` fırlatıyor
- Kullanılmayan `from sqlalchemy import text` ve `from app.db.session import engine` import'ları silindi
- İlgili test güncellendi: `NotImplementedError` bekleniyor

**Önemli #1 — Sequential health check** (`app/services/health.py`)
- `collect_health_status` artık `asyncio.gather()` ile 4 check'i paralel çalıştırıyor
- Worst-case response süresi 4×5s'den 5s'e indi

**Önemli #2 — Sparse vector eksikliği** (`app/services/collections.py`)
- `create_collection` payload'una `"sparse_vectors": {"sparse": {}}` eklendi
- Hybrid search için API üzerinden oluşturulan collection'lar da sparse-ready

**Önemli #3 — Embed model adı** (`app/config.py`)
- Default `"gemini-embedding-2"` → `"gemini-embedding-2-preview"` düzeltildi

**Küçük — Dead code** (`app/services/query.py`)
- `_rrf_merge_hits`'teki erişilemeyen `if dense_document_ids is None and sparse_document_ids is None` dalı silindi

### 📝 Checklist Güncellemeleri
- Audio loader: `[x]` → `[ ]` (120s clip split + audio embed implement edilmemiş)
- DB loader: `[x]` → `[ ]` (tenant izolasyon sorunu nedeniyle devre dışı)
- Conversation Memory 3 madde: `[ ]` → `[x]` (`chat.py`'de zaten implement edilmişti)

---

## Deploy Doğrulama Notu — 2026-03-23

Production smoke blocker paketi canlı olarak doğrulandı.

### ✅ Doğrulananlar

- `docker-compose up -d` artık build/start ediyor — `httpx==0.27.2` ile `crawl4ai==0.6.3` dependency çakışması çözüldü.
- `PgBouncer` non-root container olarak kalkıyor.
- `Langfuse` ayrı `langfuse_db` üstünde kalkıyor; app DB ile Prisma migration çakışmıyor.
- Alembic merge revision eklendi (`004_merge_heads`); temiz `ragdb_smoke` veritabanında `alembic upgrade head` başarılı geçti.
- Canlı `/health` kontrolü geçti: `postgres`, `redis`, `qdrant`, `embedder` = `up`.
- Canlı sync PDF ingest geçti:
  - `POST /ingest?mode=sync` → `201`
  - `GET /ingest/{id}` → `status: indexed`
- Canlı source-backed `/query` geçti:
  - soru: `Which invoice was paid and for which customer?`
  - cevap: `Invoice INV-1001 was paid for customer Acme Corp.`
- Canlı rate-limit geçti:
  - 61 istek → `{200: 59, 429: 2}`
  - `Retry-After` header döndü

### 🛠️ Bu doğrulamayı mümkün kılan düzeltmeler

- `CollectionsService` ile `QdrantVectorStore` aynı named dense+sparse collection şemasına çekildi.
- `ensure_collection()` mevcut collection'da `409` ile patlamaz hale getirildi.
- Sparse encoder indeks aralığı Qdrant'ın kabul ettiği 32-bit aralığa indirildi.
- Sync ingest hata yolunda `job/document` artık `failed` durumuna finalize edilir; `running/indexing` halde kalmaz.

### ⚠️ Açık Kalanlar

- `DB loader` hâlâ kapalı.
- `Latency budget enforcement` ve `Token budget enforcement` hâlâ açık.

---

## Dürüst Notlar — Sonraki Teknik Temizlik

- Integration test fixture stabilize edildi.
  Yapılan: `drop_all/create_all` kaldırıldı; fixture artık test başına `create_all + TRUNCATE` yapıyor. `tests/test_ingestion_service.py tests/test_query_service.py` suite'i `67 passed` ile temiz geçti.

- Aynı anda birden fazla `pytest` süreci açılırsa local test DB kilitlenebiliyor.
  Yapılması gereken: integration suite'i tek process ile çalıştır; stuck `pytest` process'lerini temizlemeden yeni koşu başlatma.

- `Document relationship` geniş integration suite ile de doğrulandı.
  Yapılan: `tests/test_ingestion_service.py tests/test_query_service.py` birlikte koşuldu ve geçti.

- Yeni migration eklendikçe local integration DB eski şemada kalabiliyor.
  Yapılması gereken: migration sonrası temiz test DB'de `alembic upgrade head` veya test DB reset çalıştır.
