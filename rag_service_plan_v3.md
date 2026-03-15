# RAG Service — Mimari Karar Belgesi v3.0

**Tarih:** 2026-03-15
**Değişiklikler:** PostgreSQL (SQLite kaldırıldı) · Gemini Embedding 2 (multimodal, tüm kaynak tipleri)

---

## Genel Mimari

```
Proje (Laravel / RN)
│
▼
RAG Service (FastAPI)
├── Ingestion Pipeline
│   ├── Loader (PDF / Web / Audio / Video / DB / Image / Email / Chat)
│   ├── Chunker (source-aware, parent-child)
│   └── Embedder (Gemini Embedding 2 — multimodal)
├── Registry (PostgreSQL)
├── Vector Store (Qdrant)
└── Query Pipeline
    ├── Hybrid Search (Dense + BM25/Sparse)
    ├── Reranker (Cohere Rerank-3)
    └── LLM (agnostic — openai / anthropic / gemini / ollama)
```

---

## 1. Temel Teknoloji Kararları

### 1.1 Embedding — Gemini Embedding 2

| Model | Dimension | Kullanım |
|---|---|---|
| `gemini-embedding-2` | 768 (MRL truncated) | Primary — tüm modalities |

**Kritik değişiklik:** Gemini Embedding 2, multimodal bir modeldir. Tek model ile text, image, video, audio ve PDF embed edilir. Önceki fallback model (`text-embedding-004`) kaldırıldı.

**Teknik özellikler:**
- Text: 8192 token context window
- Image: 6 image/request (PNG, JPEG)
- Video: 120 saniyeye kadar (MP4, MOV)
- Audio: native embed — transcription pipeline gerekmez
- PDF: 6 sayfaya kadar direkt embed
- 100+ dil (Türkçe dahil)
- MRL: 3072 → 1536 → **768** (seçilen — storage/kalite dengesi)
- Interleaved input: tek request'te image + text birlikte

**`task_type`:**
- İndexleme: `RETRIEVAL_DOCUMENT`
- Sorgulama: `RETRIEVAL_QUERY`

**Qdrant collection:** 768 dim, sabit. Model değişse MRL sayesinde yeniden index gerekmez.

---

### 1.2 Vector Store — Qdrant

- Docker container olarak deploy edilir
- Tek collection — izolasyon `tenant_id` + `scope_type` + `scope_id` payload filter ile
- Ayrı collection açılmaz (tenant başına değil)
- Qdrant v1.16+ native multi-tenant partitioning kullanılır

---

### 1.3 Registry / Metadata — PostgreSQL

- Docker container, başından itibaren PostgreSQL
- SQLite yok — connection pooling, RLS, migration desteği için direkt PostgreSQL
- PgBouncer: transaction pool_mode, 20–50 pool size (P3'te eklenecek)
- Alembic ile migration yönetimi

---

### 1.4 Queue — ARQ + Redis

- FastAPI ile async/await native uyum
- IO pool: embed, web, DB işlemleri
- CPU pool: video ffmpeg işlemleri (audio artık native embed)
- Failed job retry: max 3, exponential backoff
- `rag_ingestion_jobs` tablosuna yazılır

---

### 1.5 Chunking Stratejisi

| Source | Strateji | Parent | Child | Overlap |
|---|---|---|---|---|
| PDF (≤6 sayfa) | Direkt embed | Sayfa grubu | 6 sayfalık blok | — |
| PDF (>6 sayfa) | Semantic (paragraf sonu) | 1500 token | 300 token | 50 token |
| Web | Semantic (HTML temizlenmiş) | 1000 token | 250 token | 50 token |
| Audio | Speaker turn bazlı | Konuşma bloğu | 120s blok | — |
| Video | Zaman bazlı | 120s blok | 120s blok | — |
| DB | Record bazlı (flatten) | Row | Row | — |
| Image | Direkt embed | — | Per image | — |
| Email | Thread → mesaj bazlı | Thread | Mesaj | — |
| Chat | Export parse | Thread | Mesaj | — |

**Chunk kalite filtresi (text için):**
- Min 50 token → bir sonraki ile birleştir
- Max 600 token → yeniden böl
- Boş / whitespace → atla
- SHA256 duplicate → mevcut chunk_id kullan

---

### 1.6 Retrieval — Hybrid Search

```
Query
├── Gemini Embedding 2 → Dense search (Qdrant)
└── BM25 (Snowball Türkçe stemmer) → Sparse search (Qdrant)
         ↓
    RRF Fusion
         ↓
  Cohere Rerank-3
         ↓
     LLM → Response
```

**Dinamik Top-K:**

| Senaryo | search_k | threshold | rerank_k |
|---|---|---|---|
| Kısa soru-cevap | 10 | 0.75 | 2 |
| Detaylı analiz | 30 | 0.65 | 5 |
| Ses / video | 20 | 0.70 | 4 |

---

### 1.7 LLM — Agnostic

| Provider | Model örnekleri |
|---|---|
| openai | gpt-4o, gpt-4o-mini |
| anthropic | claude-sonnet-4-6, claude-haiku-4-5 |
| gemini | gemini-2.5-pro, gemini-2.0-flash |
| ollama | llama3, mistral (self-hosted) |

---

### 1.8 Auth

- `X-API-Key` + `X-Project-ID` header — her istekte
- Middleware cross-project erişimi engeller (filter servis tarafında inject edilir, client'tan gelmez)

---

## 2. Source Loader'lar

| Source | Araç / Yöntem | Değişiklik (v3) |
|---|---|---|
| PDF (≤6 sayfa) | Gemini Embedding 2 direkt | **YENİ** — pymupdf gerekmez |
| PDF (>6 sayfa) | pymupdf (layout-aware) + chunk | Aynı |
| Web | crawl4ai (JS render) | Aynı |
| Audio | Gemini Embedding 2 direkt (native audio) | **YENİ** — Whisper opsiyonel (metadata için) |
| Video | ffmpeg → 120s clip → Gemini Embedding 2 | **YENİ** — audio çıkarma gerekmez |
| DB | SQL → SummaryFormatter → text embed | Aynı |
| Image | Gemini Embedding 2 direkt | **YENİ** — Vision API caption gerekmez |
| Email | MIME parse → text embed | Aynı |
| Chat | Export parse → text embed | Aynı |

**Audio notlar:**
- Native embed için Whisper transcription gerekmez
- Ancak arama sonuçlarında "timestamp + konuşmacı" metadata göstermek istiyorsan Whisper + pyannote hâlâ faydalı (P2/P3 özelliği)
- V3'te: audio → 120s clip → Gemini Embedding 2 native embed

**Video notlar:**
- ffmpeg: video → 120s clip'lere böl (audio çıkarma değil, video clip)
- Her clip → Gemini Embedding 2 (video modality)

---

## 3. Veri Modeli (PostgreSQL)

### `rag_tenants`
```sql
id            UUID PRIMARY KEY
name          TEXT
api_key_hash  TEXT
created_at    TIMESTAMP
```

### `rag_projects`
```sql
id            UUID PRIMARY KEY
tenant_id     UUID REFERENCES rag_tenants
name          TEXT
config        JSONB  -- top_k, threshold, use_graph, latency_budget_ms, token_budget
created_at    TIMESTAMP
```

### `rag_documents`
```sql
id                    UUID PRIMARY KEY
project_id            UUID REFERENCES rag_projects
tenant_id             UUID REFERENCES rag_tenants
source_type           TEXT  -- pdf | web | audio | video | db | image | email | chat
source_ref            TEXT  -- URL, dosya yolu, tablo adı
content_hash          TEXT  -- SHA256, re-index trigger
title                 TEXT
file_size_bytes       BIGINT
version               INT DEFAULT 1
previous_document_id  UUID REFERENCES rag_documents
source_connector_id   UUID
status                TEXT  -- pending | indexing | indexed | failed
embed_model           TEXT  -- 'gemini-embedding-2'
chunk_count           INT
created_at            TIMESTAMP
embedded_at           TIMESTAMP
metadata              JSONB
```

### `rag_chunks`
```sql
id                UUID PRIMARY KEY
document_id       UUID REFERENCES rag_documents
parent_chunk_id   UUID REFERENCES rag_chunks  -- parent-child
qdrant_point_id   UUID  -- Qdrant köprüsü
chunk_index       INT
modality          TEXT  -- text | image | audio | video
token_count       INT
page_number       INT
bbox              JSONB  -- PDF koordinatları
section_title     TEXT
acl               TEXT[]
is_archived       BOOLEAN DEFAULT false
embed_model       TEXT
embed_version     TEXT
dimension         INT DEFAULT 768
created_at        TIMESTAMP
```

### `rag_ingestion_jobs`
```sql
id               UUID PRIMARY KEY
document_id      UUID REFERENCES rag_documents
job_type         TEXT  -- ingest | re_index | delete
status           TEXT  -- pending | running | completed | failed
retry_count      INT DEFAULT 0
duration_ms      INT
chunks_processed INT
error_message    TEXT
created_at       TIMESTAMP
completed_at     TIMESTAMP
```

### `rag_chunk_diff_log`
```sql
id          UUID PRIMARY KEY
job_id      UUID REFERENCES rag_ingestion_jobs
chunk_id    UUID REFERENCES rag_chunks
operation   TEXT  -- new | modified | deleted | unchanged
created_at  TIMESTAMP
```

### `rag_sync_checkpoints`
```sql
id                 UUID PRIMARY KEY
source_connector_id UUID
cursor_state       JSONB  -- connector bazlı son konum
updated_at         TIMESTAMP
```

### `tenant_secrets`
```sql
id           UUID PRIMARY KEY
tenant_id    UUID REFERENCES rag_tenants
key_type     TEXT  -- gemini | openai | anthropic | cohere
secret_hash  TEXT  -- BYOK (şifreli, implement edilmedi — sadece tablo)
created_at   TIMESTAMP
```

---

## 4. Qdrant Point Payload

```json
{
  "vector": [...],
  "payload": {
    "document_id":  "uuid",
    "chunk_id":     "uuid",
    "chunk_index":  3,
    "tenant_id":    "crm",
    "scope_type":   "tenant_user",
    "scope_id":     "tenant_abc:user_789",
    "source_type":  "audio",
    "modality":     "audio",
    "text":         "...",
    "acl":          ["role_admin", "role_user"],
    "is_archived":  false
  }
}
```

---

## 5. API Endpoints

| Method | Endpoint | Açıklama |
|---|---|---|
| `POST` | `/ingest` | Doküman ekle (async) |
| `POST` | `/ingest/batch` | Toplu doküman kuyruğa al |
| `GET` | `/ingest/{id}` | Status: pending / indexing / indexed / failed |
| `DELETE` | `/ingest/{id}` | Soft-delete (is_archived=true + Qdrant'tan sil) |
| `POST` | `/query` | Tek seferlik soru-cevap |
| `POST` | `/chat` | Conversation (Redis session ile) |
| `GET` | `/collections` | Collection listesi |
| `POST` | `/collections` | Yeni collection |
| `GET` | `/health` | Servis sağlık durumu |
| `POST` | `/schedules` | Cron bazlı re-index |

### `/ingest` Async Akışı
```
POST /ingest → document_id döner (hemen)
       ↓
ARQ worker: load → chunk → embed → Qdrant upsert
       ↓
GET /ingest/{id} → status: pending | indexing | indexed | failed
```

---

## 6. Multi-Tenant İzolasyon

### Üç Katman

| Katman | Alan | Açıklama |
|---|---|---|
| 1 | `tenant_id` | En üst seviye (CRM, sports app, personal tool) |
| 2 | `scope_type` | `tenant` / `user` / `tenant_user` |
| 3 | `scope_id` | Alt kimlik (user ID, tenant kodu veya kombinasyon) |

### Proje Konfigürasyonları

| Proje | tenant_id | scope_type | scope_id |
|---|---|---|---|
| Mobil app | sports_app | user | user_456 |
| CRM — firma bazlı | crm | tenant | tenant_abc |
| CRM — kullanıcı bazlı | crm | tenant_user | tenant_abc:user_789 |
| Kişisel araç | personal | tenant | null |

### Query Filter Injection (middleware, client'tan gelmiyor)
```python
filter = {
    "tenant_id": request.tenant_id,
    "scope_id":  request.scope_id
}
```

---

## 7. LangGraph — Opsiyonel Query Pipeline

Config ile toggle edilir. Basit soru-cevap için direkt pipeline yeterli.

### Self-RAG Akışı
```
Query
  ↓
[classify] — basit mi, karmaşık mı?
  ↓
[retrieve] — hybrid search + rerank
  ↓
[grade] — chunk'lar yeterli mi? (LLM değerlendirir)
  ├─ Yetersiz → [rewrite] → [retrieve] (max 2 tur)
  └─ Yeterli ↓
[generate] — LLM cevap üret
  ↓
[hallucination_check] — cevap context'e uygun mu?
  ↓
Response
```

### Config Toggle
```json
{
  "query": "...",
  "project_id": "sports_app",
  "config": {
    "use_graph":       true,
    "max_rewrite":     2,
    "grade_threshold": 0.7,
    "latency_budget_ms": 5000,
    "token_budget":    4000,
    "provider":        "anthropic"
  }
}
```

---

## 8. Observability

### Ingestion Log
```json
{
  "event":       "chunk_indexed",
  "document_id": "uuid",
  "chunk_index": 3,
  "modality":    "text",
  "token_count": 287,
  "embed_model": "gemini-embedding-2",
  "embed_ms":    142,
  "project_id":  "sports_app"
}
```

### Query Log
```json
{
  "event":             "query_completed",
  "query_hash":        "sha256...",
  "search_k":          20,
  "rerank_k":          3,
  "reranker_ms":       198,
  "llm_ms":            1240,
  "prompt_tokens":     820,
  "completion_tokens": 310,
  "top_chunk_score":   0.91,
  "project_id":        "sports_app"
}
```

> Query içeriği loglanmaz — sadece SHA256 hash. GDPR uyumu.

---

## 9. Circuit Breaker

| Servis | Hata | Davranış |
|---|---|---|
| Qdrant | Down | Query 503, ingestion kuyruğa alınır |
| Gemini Embedding 2 | Rate limit | Ingestion duraklatılır, retry queue |
| Gemini Embedding 2 | Down | Ingestion durdurulur, 503 |
| Cohere reranker | Down | Rerank atlanır, sadece RRF skoru |
| LLM | Down | Context döner, LLM yanıtı yok, 503 |

---

## 10. Re-index & Versioning

```
Yeni içerik geldi
      ↓
content_hash hesapla
      ↓
Hash aynı mı? → Evet: işlem yok
      ↓ Hayır
Yeni chunk'ları hesapla
      ↓
Chunk hash'lerini karşılaştır (eski vs yeni)
      ↓
Sadece değişen chunk'lar:
  - Qdrant'tan sil (qdrant_point_id ile)
  - Yeniden embed et
  - Qdrant'a ekle
  - PostgreSQL'i güncelle
  - rag_chunk_diff_log'a yaz
```

---

## 11. Rate Limiting

| Katman | Limit | Kapsam |
|---|---|---|
| `/query` | 60 req/dk | project_id bazında |
| `/ingest` | 20 req/dk | project_id bazında |
| Gemini Embedding API | Token bucket | Global, Gemini quota'ya göre |
| LLM API | Token bucket | Global, provider quota'ya göre |

Redis sliding window counter. Limit aşılınca 429 + `Retry-After` header.

---

## 12. Caching

```
cache_key = sha256(query + tenant_id + scope_id + collection)
Redis'te var mı? → Evet: direkt dön (0ms)
                   Hayır: pipeline çalıştır → cache'e yaz (TTL: 1 saat)
Cache invalidation: collection re-index edilince
```

---

## 13. Health Check

```json
GET /health → {
  "status":   "ok | degraded | down",
  "qdrant":   "ok | down",
  "postgres": "ok | down",
  "redis":    "ok | down",
  "embedder": "ok | rate_limited | down"
}
```

---

## 14. Docker Compose Stack

```
FastAPI (RAG Service)
PostgreSQL
Qdrant
Redis
Langfuse (self-host, observability)
```

---

## 15. SaaS Yolculuğu — 4 Aşama

### Aşama 1 — Şu An: Single-Operator
- Multi-tenant mimari hazır (tenant_id + scope)
- Manuel API key yönetimi
- Rate limiting aktif
- Billing yok

### Aşama 2 — Yakın: Internal Olgunlaşma
- Filament admin panel
- Usage dashboard (token/query maliyet raporu)
- Webhook callback sistemi
- Laravel SDK (HTTP wrapper)
- Staging ortamı

### Aşama 3 — SaaS Beta
- Self-serve kayıt
- Free tier + hard limit enforcement
- Stripe (Starter / Growth plan)
- Public docs

### Aşama 4 — SaaS GA
- SSO/SAML
- Enterprise self-host
- n8n / Zapier / Make.com node
- PII maskeleme (Presidio)
- Retrieval quality analytics

---

## 16. Kararlar Özeti

| Konu | v2 Kararı | v3 Kararı |
|---|---|---|
| Registry | SQLite (→ PostgreSQL) | **PostgreSQL (başından)** |
| Embedding | gemini-embedding-exp-03-07 + fallback | **gemini-embedding-2 (tek model, multimodal)** |
| Embedding dim | 768 (truncated) | **768 (MRL truncated, default 3072'den)** |
| Audio loader | Whisper + pyannote | **Gemini Embedding 2 native (Whisper opsiyonel)** |
| Image loader | Gemini Vision → caption | **Gemini Embedding 2 direkt embed** |
| Video loader | ffmpeg → audio → AudioLoader | **ffmpeg → 120s clip → Gemini Embedding 2** |
| PDF loader | pymupdf her zaman | **≤6 sayfa: direkt embed / >6 sayfa: pymupdf** |
| Text context | ~2048 token | **8192 token** |
| Worker pool | CPU (Whisper) + IO (embed) | **IO pool (embed, web, DB) + CPU pool (video ffmpeg)** |
| LLM | Agnostic | **Agnostic (değişmedi)** |
| Observability | Structured JSON + Langfuse | **Değişmedi** |
