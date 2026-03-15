# RAG Service — Proje Planı & Checklist

**Strateji:** Önce kendi projeler (CRM, Sports App), sonra SaaS  
**Stack:** FastAPI + PostgreSQL + Qdrant + Redis + ARQ

---

## P1 — Core Altyapı (Servis çalışmadan önce tamamlanmalı)

### Proje İskeleti
- [ ] FastAPI proje yapısı oluştur (`app/`, `workers/`, `tests/`)
- [ ] Docker Compose: FastAPI + PostgreSQL + Qdrant + Redis + Langfuse
- [ ] `.env` yapısı ve config yönetimi (`pydantic-settings`)
- [ ] X-API-Key + X-Project-ID middleware (auth)
- [ ] `/health` endpoint — Qdrant, PostgreSQL, Redis, Embedder durumu

### Veritabanı (PostgreSQL)
- [ ] `rag_tenants` tablosu
- [ ] `rag_projects` tablosu
- [ ] `rag_documents` tablosu — `version`, `previous_document_id`, `source_connector_id`, `file_size_bytes`, `title` dahil
- [ ] `rag_chunks` tablosu — `parent_chunk_id`, `page_number`, `bbox`, `section_title`, `acl`, `is_archived`, `embed_model`, `embed_version` dahil
- [ ] `rag_ingestion_jobs` tablosu — job_type, status, retry_count, duration_ms, chunks_processed
- [ ] `rag_chunk_diff_log` tablosu — operation: new/modified/deleted/unchanged
- [ ] `rag_sync_checkpoints` tablosu — connector bazlı cursor_state
- [ ] `tenant_secrets` tablosu — BYOK için şema (implement etme, sadece tablo)
- [ ] Alembic migration yapısı

### Ingestion Pipeline
- [ ] Source loader: PDF (pymupdf, layout-aware)
- [ ] Source loader: Web (crawl4ai, JS render)
- [ ] Source loader: Audio (Whisper large-v3 + pyannote diarization)
- [ ] Source loader: Video (ffmpeg → audio → AudioLoader)
- [ ] Source loader: DB (SQL → text serializer)
- [ ] Source loader: Image (Gemini Vision → caption)
- [ ] Source loader: Email (MIME parse)
- [ ] Source loader: Chat export (WhatsApp, Slack)
- [ ] SummaryFormatter — DB/JSON/tablo verisini natural language'a çevir
- [ ] Source-aware chunker — PDF/Web/Audio/DB/Email stratejileri
- [ ] Parent-child chunk oluşturma — `parent_chunk_id` FK ile
- [ ] Chunk kalite filtresi — min 50 token, max 600 token, boş/duplicate atla
- [ ] `bbox` ve `page_number` PDF chunk'larına eklenmesi
- [ ] Content hash (SHA256) — document ve chunk seviyesi
- [ ] Büyük dosya: URL pipeline (Hetzner Object Storage → Python indir)
- [ ] Büyük dosya: Base64 pipeline (≤50MB)

### Embedding
- [ ] Gemini `gemini-embedding-exp-03-07` primary embedder (768 dim, truncated)
- [ ] Gemini `text-embedding-004` fallback embedder
- [ ] `task_type`: RETRIEVAL_DOCUMENT (index) / RETRIEVAL_QUERY (query)
- [ ] Embedding versioning — `embed_model`, `embed_version`, `dimension` kolonu

### Vector Store (Qdrant)
- [ ] Collection oluşturma — 768 dim, sabit
- [ ] Chunk upsert — payload: tenant_id, scope_type, scope_id, source_type, acl
- [ ] Qdrant ↔ PostgreSQL köprüsü — `qdrant_point_id`
- [ ] Soft-delete — `is_archived=True` + Qdrant'tan sil

### Queue (ARQ + Redis)
- [ ] ARQ worker yapısı — IO pool (embed, web, DB) + CPU pool (Whisper, ffmpeg)
- [ ] `VectorIngestJob` — load → chunk → embed → upsert
- [ ] Failed job retry (max 3) — `rag_ingestion_jobs` tablosuna yaz
- [ ] Sync/Async mod — `/ingest?mode=sync|async`

### API Endpoints
- [ ] `POST /ingest` — async, document_id döner
- [ ] `POST /ingest/batch` — toplu doküman kuyruğa al
- [ ] `GET /ingest/{id}` — status: pending/indexing/indexed/failed
- [ ] `DELETE /ingest/{id}` — doküman + chunk sil (soft-delete)
- [ ] `POST /query` — tek seferlik soru-cevap
- [ ] `POST /chat` — conversation (Redis session ile)
- [ ] `GET /collections` — collection listesi
- [ ] `POST /collections` — yeni collection
- [ ] `GET /health`

---

## P2 — Query Pipeline & Gelişmiş Özellikler

### Retrieval
- [ ] Dense search — Gemini embed → Qdrant
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
- [ ] Langfuse Docker Compose'a ekle (self-host)
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
- [ ] Structured JSON log — ingestion eventi (chunk_indexed, embed_ms, token_count)
- [ ] Structured JSON log — query eventi (query_hash, reranker_ms, llm_ms, top_chunk_score)
- [ ] Query içeriği loglanmaz — sadece SHA256 hash (GDPR)
- [ ] Embedding versioning — stale chunk tespiti, ARQ kuyruğuna al

### Diğer
- [ ] Ingestion webhook callback — HMAC-SHA256 imzalı, `callback_url` desteği
- [ ] Rate limiting — Redis sliding window, project_id bazlı, 429 + Retry-After
- [ ] Circuit breaker — Qdrant/Gemini/Cohere/LLM per-service kurallar
- [ ] Confidence score — top chunk score ortalaması, düşükse uyarı
- [ ] SummaryFormatter — DB/JSON/tablo verisini natural language'a çevir (query expansion dahil)
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
- [ ] Multimodal query — görsel ile sorgulama (Gemini Vision embed)
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

## Notlar

| Konu | Karar |
|---|---|
| Registry | PostgreSQL (Docker) — SQLite değil |
| Embedding dim | 768 sabit (truncated) — collection değişmez |
| Worker | CPU pool (Whisper/ffmpeg) + IO pool (embed/web) ayrı |
| Büyük dosya | URL via Hetzner Object Storage (≥50MB) |
| LLM | Agnostic — openai/anthropic/gemini/ollama provider abstraction |
| Observability | Structured JSON log + Langfuse (self-host) |
| Deployment | Ayrı belgede (Docker Compose, Nginx, Hetzner, Dokploy) |
