# RAG Service — Checklist v3.0

**Strateji:** Önce kendi projeler (CRM, Sports App), sonra SaaS
**Stack:** FastAPI + PostgreSQL + Qdrant + Redis + ARQ + Langfuse
**Embedding:** Gemini Embedding 2 (multimodal — text, image, audio, video, PDF)

---

## P1 — Core Altyapı (Servis çalışmadan önce tamamlanmalı)

### Proje İskeleti
- [x] FastAPI proje yapısı oluştur (`app/`, `workers/`, `tests/`)
- [x] Docker Compose: FastAPI + PostgreSQL + Qdrant + Redis + Langfuse
- [x] `.env` yapısı ve config yönetimi (`pydantic-settings`)
- [x] X-API-Key + X-Project-ID middleware (auth)
- [x] `/health` endpoint — Qdrant, PostgreSQL, Redis, Embedder durumu

### Veritabanı (PostgreSQL)
- [x] `rag_tenants` tablosu
- [x] `rag_projects` tablosu — `config` JSONB dahil (top_k, threshold, latency_budget_ms, token_budget)
- [x] `rag_documents` tablosu — `version`, `previous_document_id`, `source_connector_id`, `file_size_bytes`, `title`, `embed_model` dahil
- [x] `rag_chunks` tablosu — `parent_chunk_id`, `modality`, `page_number`, `bbox`, `section_title`, `acl`, `is_archived`, `embed_model`, `embed_version`, `dimension` dahil
- [x] `rag_ingestion_jobs` tablosu — job_type, status, retry_count, duration_ms, chunks_processed
- [x] `rag_chunk_diff_log` tablosu — operation: new/modified/deleted/unchanged
- [x] `rag_sync_checkpoints` tablosu — connector bazlı cursor_state
- [x] `tenant_secrets` tablosu — BYOK için şema (implement etme, sadece tablo)
- [x] Alembic migration yapısı

### Ingestion Pipeline

#### Source Loaders
- [x] PDF loader — ≤6 sayfa: Gemini direct PDF path / >6 sayfa: pymupdf layout-aware chunking
- [x] Structured loader — generic `records[]` → LLM semantic formatter → text embed (rule-based fallback)
- [x] Web loader — crawl4ai (JS render, nav/footer temizleme, static fallback)
- [ ] Audio loader — Gemini Embedding 2 native embed (120s clip'lere böl)
- [ ] Video loader — ffmpeg → 120s clip → Gemini Embedding 2 (video modality)
- [x] DB loader — SQL → SummaryFormatter → text embed
- [x] Image loader — Gemini Embedding 2 direkt embed (PNG, JPEG)
- [ ] Email loader — MIME parse → text embed
- [ ] Chat loader — WhatsApp / Slack export parse

#### Pipeline
- [x] SummaryFormatter — DB/JSON/tablo verisini natural language'a çevir (rule-based + structured LLM semantic path)
- [x] Source-aware chunker — pdf/web stratejileri
- [x] Parent-child chunk oluşturma — `parent_chunk_id` FK ile
- [x] Chunk kalite filtresi (text) — boş/duplicate atla, min/max split uygula
- [x] `bbox` ve `page_number` PDF chunk'larına eklenmesi (pymupdf path)
- [x] Content hash (SHA256) — document ve chunk seviyesi
- [x] Büyük dosya: URL pipeline (Hetzner Object Storage → Python indir)
- [x] Büyük dosya: Base64 pipeline (≤50MB)

### Embedding (Gemini Embedding 2)
- [x] `gemini-embedding-2` entegrasyonu — multimodal API çağrısı
- [x] `task_type`: RETRIEVAL_DOCUMENT (index) / RETRIEVAL_QUERY (query)
- [x] MRL dimension ayarı — 768 (default 3072'den truncate)
- [x] Embedding versioning — `embed_model`, `embed_version`, `dimension` kolonu
- [x] Rate limit handler + retry (exponential backoff)

### Vector Store (Qdrant)
- [x] Collection oluşturma — 768 dim, sabit
- [x] Chunk upsert — payload: tenant_id, scope_type, scope_id, source_type, modality, acl
- [x] Qdrant ↔ PostgreSQL köprüsü — `qdrant_point_id`
- [x] Soft-delete — `is_archived=True` + Qdrant'tan sil

### Queue (ARQ + Redis)
- [x] ARQ worker yapısı — pdf/web için gerçek async IO worker
- [x] `VectorIngestJob` — pdf/web için load → chunk → embed → upsert
- [x] Failed job retry (max 3, exponential backoff) — `rag_ingestion_jobs` tablosuna yaz
- [x] Sync/Async mod — `/ingest?mode=sync|async`

### API Endpoints
- [x] `POST /ingest` — async, document_id döner
- [x] `POST /ingest/batch` — toplu doküman kuyruğa al
- [x] `GET /ingest/{id}` — status: pending/indexing/indexed/failed
- [x] `DELETE /ingest/{id}` — doküman + chunk sil (soft-delete)
- [x] `POST /query` — tek seferlik soru-cevap
- [x] `POST /chat` — conversation (Redis session ile)
- [x] `GET /collections` — collection listesi
- [x] `POST /collections` — yeni collection
- [x] `GET /health`

---

## P2 — Query Pipeline & Gelişmiş Özellikler

### Retrieval
- [ ] Dense search — Gemini Embedding 2 → Qdrant
- [ ] Sparse search — BM25 (Snowball Türkçe stemmer) → Qdrant
- [ ] RRF fusion — dense + sparse birleştir
- [ ] Cohere Rerank-3 entegrasyonu
- [ ] Dinamik top-K ve score threshold — senaryo bazlı config
- [ ] Multi-collection query — `collections[]` + `merge_strategy`
- [ ] Negative filtering — `exclude_sources`, `exclude_documents`
- [ ] Chunk seviyesi ACL — `acl[]` payload filter
- [ ] Parent-child resolution — child bul → parent getir

### LangGraph Pipeline
- [ ] Direkt pipeline (basit soru-cevap)
- [ ] LangGraph Self-RAG akışı — classify → retrieve → grade → rewrite → generate → hallucination_check
- [ ] Latency budget enforcement — `latency_budget_ms` aşınca early abort
- [ ] Token budget enforcement — `token_budget` aşınca generate kısalt
- [ ] Config toggle — `use_graph: true/false`

### Langfuse Entegrasyonu
- [x] Langfuse Docker Compose'a ekle (self-host)
- [ ] FastAPI pipeline'larına `@observe` decorator
- [ ] LangGraph node'larına trace/span ekleme
- [ ] Maliyet ve latency dashboard kurulumu

### Conversation Memory
- [ ] Redis session yönetimi — `POST /chat` session_id döner
- [ ] Son 6 tur sakla, TTL 30 dakika
- [ ] Takip sorusunda history otomatik inject

### Caching
- [ ] Query cache — `sha256(query + tenant_id + scope_id)` → Redis TTL 1 saat
- [ ] Cache invalidation — collection re-index edilince

### Re-index & Versioning
- [ ] Document versioning — `version++`, `previous_document_id`
- [ ] Chunk-level hash karşılaştırma — sadece değişen chunk'lar embed edilir
- [ ] Diff log yazımı — `rag_chunk_diff_log` her ingestion'da doldur
- [ ] Scheduled re-index — `POST /schedules`, cron bazlı ARQ job
- [ ] `rag_sync_checkpoints` — connector bazlı cursor_state güncelleme

### Observability
- [ ] Structured JSON log — ingestion (chunk_indexed, modality, embed_ms, token_count)
- [ ] Structured JSON log — query (query_hash, reranker_ms, llm_ms, top_chunk_score)
- [ ] Query içeriği loglanmaz — sadece SHA256 hash (GDPR)
- [ ] Embedding versioning — stale chunk tespiti, ARQ kuyruğuna al

### Diğer
- [ ] Audio metadata pipeline (opsiyonel) — Whisper + pyannote diarization (timestamp + speaker metadata için)
- [ ] Ingestion webhook callback — HMAC-SHA256 imzalı, `callback_url` desteği
- [ ] Rate limiting — Redis sliding window, project_id bazlı, 429 + Retry-After
- [ ] Circuit breaker — Qdrant/Gemini/Cohere/LLM per-service kurallar
- [ ] Confidence score — top chunk score ortalaması, düşükse uyarı
- [ ] Query expansion — sinonim sözlüğü + LLM genişletme

---

## P3 — Production Olgunlaşma

### Veri Kalitesi
- [ ] Semantic deduplication — embedding similarity > 0.97 ise atla
- [ ] Adaptive chunking — içerik yoğunluğuna göre otomatik chunk size
- [ ] RAG Evaluation Pipeline — RAGAS metrikleri (faithfulness, answer_relevancy, context_recall)
- [ ] Feedback loop — `POST /feedback` (rating, chunk_ids) → kötü chunk'ları düşür

### Ölçek
- [ ] Qdrant post-filtering fetch — sadece ID+metadata Qdrant'ta, metin PostgreSQL'den
- [ ] PostgreSQL partition stratejisi — tiered: shared (<100K chunk), dedicated (≥100K)
- [ ] PgBouncer — transaction pool_mode, 20-50 pool size
- [ ] Document relationship — `related_chunks` metadata, bölümler arası referans

### Admin & Yönetim
- [ ] Filament admin panel — tenant listesi, API key yönetimi
- [ ] Usage dashboard — proje bazlı token/query maliyet raporu
- [ ] Laravel SDK — HTTP wrapper, her projede tekrar yazma
- [ ] Staging ortamı — ayrı Qdrant + PostgreSQL instance

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
