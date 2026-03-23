# RAG Service Handbook

Bu doküman geliştirici ve operasyon ekibi içindir. Amaç, servisin bugün ne yaptığını, bunu hangi akışlarla yaptığını ve üretimde nasıl işletileceğini tek yerde toplamaktır.

## 1. Amaç ve Kapsam

Bu servis, farklı uygulamalardan gelen verileri tek bir RAG altyapısında toplar, işler, vektörler ve sorgulanabilir hale getirir.

Bugün hedeflenen kullanım:

- CRM, mobil uygulama, içerik sitesi gibi sistemlerden veri ingest etmek
- tenant ve project bazlı izole retrieval yapmak
- kullanıcı sorularına kaynak destekli cevap üretmek
- düzenli senkronizasyon, yeniden indeksleme ve operasyonel gözlemlenebilirlik sağlamak

Bu servis bir SaaS paneli değildir. Çok kiracılı çalışma temeli vardır ama self-serve kayıt, ödeme, admin panel ve benzeri SaaS yüzeyi kapsam dışındadır.

## 2. Sistem Özeti

Ana stack:

- `FastAPI`: HTTP API yüzeyi
- `PostgreSQL`: tenant, project, document, chunk, job ve metadata kaynağı
- `Qdrant`: dense ve sparse retrieval için vektör veritabanı
- `Redis`: queue, rate limit, query cache
- `ARQ`: async ingest ve schedule worker
- `Langfuse`: trace ve span gözlemlenebilirliği
- `PgBouncer`: runtime DB connection pooling

Çalışma topolojisi:

- `api` servisi HTTP isteklerini alır
- `worker` servisi async ingest ve schedule işlerini çalıştırır
- `postgres` ana uygulama verisini tutar
- `langfuse_db` sadece Langfuse içindir
- `qdrant` retrieval vektörlerini tutar
- `redis` queue/cache/rate-limit için kullanılır
- `pgbouncer` runtime DB bağlantılarını transaction pool modunda toplar

Ana giriş noktaları:

- [router.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/api/router.py)
- [docker-compose.yml](/Users/ibrahim/Desktop/rag-pipeline/rag-service/docker-compose.yml)
- [config.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/config.py)

## 3. Çalışan Kabiliyetler

Bugün üretimde kullanılabilecek ana kabiliyetler şunlardır:

### Ingest

- PDF ingest
- Web ingest
- Structured JSON ingest
- Image ingest
- Audio ingest
- sync ve async ingest modları
- batch async ingest
- source-aware chunking
- parent-child chunk modeli
- document versioning
- chunk hash compare ve unchanged vector reuse
- diff log yazımı
- scheduled re-index
- stale embedding requeue
- semantic deduplication

### Retrieval ve Answering

- dense search
- sparse search
- varsayılan hybrid retrieval
- RRF fusion
- Cohere rerank
- query expansion
- confidence score
- direct question-answer pipeline
- source-backed answer
- chat endpoint ve session memory

### Operasyonel Kabiliyetler

- structured JSON logging
- query hash logging
- Langfuse tracing
- query cache
- cache invalidation
- rate limiting
- circuit breaker
- health checks
- PgBouncer uyumlu runtime DB bağlantısı

## 4. Veri Modeli

Ana tablolar:

- `rag_tenants`
- `rag_projects`
- `rag_documents`
- `rag_chunks`
- `rag_ingestion_jobs`
- `rag_chunk_diff_log`
- `rag_sync_checkpoints`
- `rag_schedules`
- `tenant_secrets`

Temel ilişki:

- her istek bir `project_id` bağlamında çalışır
- ingest ile bir `rag_document` ve buna bağlı `rag_chunks` oluşur
- vektör karşılığı Qdrant'ta tutulur, köprü alanı `qdrant_point_id` üzerinden sağlanır
- query aşamasında skor ve metadata Qdrant'tan, metin içeriği PostgreSQL'den alınır

Referans:

- [db.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/models/db.py)

## 5. API Yüzeyi

Ana endpoint'ler:

- `GET /health`
- `POST /collections`
- `POST /ingest`
- `POST /ingest/batch`
- `GET /ingest/{job_id}`
- `DELETE /ingest/{job_id}`
- `POST /query`
- `POST /chat`
- `POST /schedules`

Auth modeli:

- tüm korumalı çağrılarda `X-API-Key`
- tenant/project bağlamı için `X-Project-ID`

Referans:

- [auth.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/middleware/auth.py)
- [deps.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/deps.py)

## 6. Ingest Nasıl Çalışır

Genel ingest akışı:

1. API isteği alınır.
2. `rag_documents` ve `rag_ingestion_jobs` kaydı açılır.
3. Kaynağa göre uygun loader çalışır.
4. Gerekirse içerik doğal dile çevrilir.
5. Chunking uygulanır.
6. Parent ve child chunk row'ları hazırlanır.
7. Dense ve gerekiyorsa sparse retrieval için vektör hazırlanır.
8. PostgreSQL chunk row'ları ve Qdrant point'leri yazılır.
9. Job `indexed` veya hata durumunda `failed` olur.

Ana servis:

- [ingestion.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/ingestion.py)

### 6.1 PDF

Akış:

- küçük PDF ise Gemini direct PDF path
- büyük PDF ise PyMuPDF ile layout parse
- page, bbox ve section metadata çıkarılır
- parent-child chunk yapısı kurulur

Referans:

- [loaders.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/loaders.py)
- [document_ai.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/document_ai.py)

### 6.2 Web

Akış:

- önce `crawl4ai` ile render/crawl denenir
- başarısızsa static HTML fallback
- navigation/footer benzeri gürültü temizlenir
- temiz metin chunk'lanır

Referans:

- [loaders.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/loaders.py)

### 6.3 Structured JSON

Akış:

- dış sistemden `records[]` gelir
- SummaryFormatter bunu semantik doğal dile çevirir
- LLM semantic formatter başarısızsa rule-based fallback çalışır
- çıkan metin normal text chunk gibi embed edilir

Referans:

- [summary_formatter.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/summary_formatter.py)
- [ingest.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/schemas/ingest.py)

### 6.4 Image

Akış:

- PNG veya JPEG doğrudan multimodal embedding yoluna girer
- metadata PostgreSQL'de saklanır
- vector Qdrant'a yazılır

Referans:

- [loaders.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/loaders.py)
- [embedder.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/embedder.py)

### 6.5 Audio

Akış:

- audio 120 saniyelik clip pencerelerine bölünür
- her clip için native multimodal embedding alınır
- clip metadata ve vector yazılır

Referans:

- [media.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/media.py)
- [ingestion.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/ingestion.py)

## 7. Retrieval ve Answering Nasıl Çalışır

Varsayılan sorgu akışı:

1. Kullanıcı sorusu alınır.
2. Query expansion çalışır.
3. Dense retrieval ve sparse retrieval birlikte çalışır.
4. Sonuçlar RRF ile birleştirilir.
5. Cohere rerank devredeyse adaylar yeniden sıralanır.
6. Qdrant'tan sadece kimlik ve metadata gelir.
7. Asıl snippet ve parent context PostgreSQL chunk içeriğinden çekilir.
8. Prompt builder context oluşturur.
9. LLM final cevabı üretir.
10. LLM hata verirse fallback answer döner.
11. Response içinde sources, retrieval_context ve confidence alanları verilir.

Ana servis:

- [query.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/query.py)

Destek servisleri:

- [query_expansion.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/query_expansion.py)
- [vector_store.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/vector_store.py)
- [reranker.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/reranker.py)
- [llm.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/llm.py)
- [prompts.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/prompts.py)

### Retrieval modları

- `hybrid`: varsayılan, dense + sparse + RRF
- `dense`: sadece dense
- `sparse`: sadece sparse

### Query response ne döner

- `answer`
- `retrieval_mode`
- `confidence_score`
- `confidence_warning`
- `retrieval_context[]`
- `sources[]`

## 8. Chat Nasıl Çalışır

`/chat`, query hattının hafif session-memory sarmalayıcısıdır.

Akış:

- `message` alınır
- `session_id` varsa önceki mesajlar store'dan yüklenir
- query servisiyle cevap üretilir
- yeni oturum veya mevcut oturum güncellenir

Referans:

- [chat.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/chat.py)

Not:

- Bu canlı chatbot orchestration sistemi değildir
- geçmiş sohbet export ingest etmek için ayrı bir `Chat loader` henüz yoktur

## 9. Queue, Schedule ve Re-index

### Async ingest

- `mode=async` ile job kuyruğa yazılır
- worker ARQ üzerinden işi işler

Referans:

- [ingest.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/workers/tasks/ingest.py)

### Schedule

- `POST /schedules` cron tanımı yazar
- worker dakikalık tick ile due schedule'ları tarar
- varsa ingest job enqueue eder

Referans:

- [schedules.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/schedules.py)
- [schedules.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/workers/tasks/schedules.py)

### Re-index ve versioning

- aynı `project_id + source_ref` için yeni ingest yeni document version açar
- eski sürüm `superseded` yapılır
- unchanged chunk'lar hash ile tespit edilir
- eski vector gerekiyorsa reuse edilir
- diff kayıtları `rag_chunk_diff_log` tablosuna yazılır
- stale embedding sürümleri saatlik tarama ile yeniden kuyruğa alınır

## 10. Operasyonel Davranışlar

### Query cache

- request fingerprint üzerinden Redis key üretilir
- hit varsa retrieval/generation yolu atlanır
- ilgili ingest veya delete sonrası project bazlı invalidation yapılır

Referans:

- [query_cache.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/query_cache.py)

### Rate limiting

Sadece ağır endpoint'lere uygulanır:

- `/query`
- `/chat`
- `/ingest`
- `/ingest/batch`

Davranış:

- Redis sliding window
- `429 Too Many Requests`
- `Retry-After` header
- Redis down ise fail-open

Referans:

- [rate_limit.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/rate_limit.py)

### Circuit breaker

Korunan dış servisler:

- Qdrant
- Gemini embed
- Gemini LLM
- Cohere rerank

Davranış:

- `closed/open/half_open`
- provider açık devre ise dış çağrı yapılmaz
- query tarafında mümkün olan yerde fallback korunur

Referans:

- [circuit_breaker.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/circuit_breaker.py)

### Observability

İki seviye vardır:

- stdout JSON log
- Langfuse trace/span

Loglanan güvenli alan örnekleri:

- `project_id`
- `query_hash`
- `retrieval_mode`
- `embed_ms`
- `reranker_ms`
- `llm_ms`
- `top_chunk_score`

Ham soru, tam prompt ve chunk içeriği log veya trace metadata'ya gönderilmez.

Referans:

- [observability.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/observability.py)
- [tracing.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/services/tracing.py)

### PgBouncer

Runtime davranışı:

- `api` ve `worker` PgBouncer üzerinden bağlanır
- SQLAlchemy `NullPool` ile çalışır
- `prepared_statement_cache_size=0` kullanılır
- Alembic migration'lar `DATABASE_DIRECT_URL` ile doğrudan Postgres'e gider

Referans:

- [session.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/app/db/session.py)
- [env.py](/Users/ibrahim/Desktop/rag-pipeline/rag-service/migrations/env.py)

## 11. Nasıl Kullanılır

### 11.1 Servisi ayağa kaldırma

```bash
cd rag-service
docker-compose up -d --build
```

Beklenen servisler:

- `api`
- `worker`
- `postgres`
- `langfuse_db`
- `pgbouncer`
- `redis`
- `qdrant`
- `langfuse`

### 11.2 Health kontrolü

```bash
curl -sS http://127.0.0.1:8000/health
```

Beklenen durum:

- `postgres: up`
- `redis: up`
- `qdrant: up`
- `embedder: up`

### 11.3 Collection oluşturma

```bash
curl -sS -X POST http://127.0.0.1:8000/collections \
  -H 'X-API-Key: <api-key>' \
  -H 'X-Project-ID: <project-id>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"rag_chunks"}'
```

### 11.4 Structured ingest örneği

```bash
curl -sS -X POST 'http://127.0.0.1:8000/ingest?mode=sync' \
  -H 'X-API-Key: <api-key>' \
  -H 'X-Project-ID: <project-id>' \
  -H 'Content-Type: application/json' \
  -d '{
    "source_type": "structured",
    "title": "crm snapshot",
    "records": [
      {
        "customer": "Acme Corp",
        "invoice_no": "INV-1001",
        "status": "paid",
        "amount": 1200
      }
    ],
    "scope_type": "tenant",
    "scope_id": "acme",
    "entity_type": "invoice",
    "record_ids": ["INV-1001"],
    "tags": ["crm", "billing"],
    "acl": ["company:acme"]
  }'
```

### 11.5 Query örneği

```bash
curl -sS -X POST http://127.0.0.1:8000/query \
  -H 'X-API-Key: <api-key>' \
  -H 'X-Project-ID: <project-id>' \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Which invoice was paid and for which customer?",
    "retrieval_mode": "hybrid",
    "acl": ["company:acme"],
    "scope_type": "tenant",
    "scope_id": "acme"
  }'
```

### 11.6 Schedule örneği

```bash
curl -sS -X POST http://127.0.0.1:8000/schedules \
  -H 'X-API-Key: <api-key>' \
  -H 'X-Project-ID: <project-id>' \
  -H 'Content-Type: application/json' \
  -d '{
    "cron_expr": "0 3 * * *",
    "ingest": {
      "source_type": "structured",
      "title": "daily crm sync",
      "records": [{"customer":"Acme Corp","status":"active"}],
      "mode": "async"
    }
  }'
```

## 12. Canlı Olarak Doğrulanmış Akışlar

2026-03-23 itibarıyla şu akışlar gerçek servisler üzerinde doğrulandı:

- `docker-compose up -d --build`
- temiz bir Postgres veritabanında `alembic upgrade head`
- canlı `/health`
- canlı sync PDF ingest
- `GET /ingest/{job_id}` ile `indexed` durumu
- canlı source-backed `/query`
- canlı rate limit ve `Retry-After`

Bu doğrulama, checklist içindeki deploy notu ile uyumludur:

- [rag_service_checklist_v3.md](/Users/ibrahim/Desktop/rag-pipeline/rag_service_checklist_v3.md)

## 13. Bilinen Sınırlar ve Açık Konular

Şu an açık veya bilerek devre dışı bırakılmış başlıklar:

- `DB loader` kapalıdır
- `Video loader` yoktur
- `Email loader` yoktur
- `Chat loader` ingest tarafında yoktur
- `latency_budget_ms` enforcement uygulanmıyor
- `token_budget` enforcement uygulanmıyor
- tam bir RAG evaluation pipeline yoktur
- feedback loop henüz yoktur

Bu yüzden sistem üretimde kullanılabilir durumdadır, ancak özellikle bütçe zorlaması ve DB loader ihtiyacı olan senaryolarda ek iş gerekir.

## 14. Ne Zaman Bu Servis Uygundur

Bu servis şu senaryolarda uygundur:

- birden fazla uygulamadan gelen veriyi tek retrieval katmanında toplamak
- günlük veya periyodik ingest ile bilgi tabanını güncel tutmak
- tenant/project izolasyonlu source-backed cevap üretmek
- PDF, web, structured, image ve audio verileri aynı altyapıda işlemek

Şu senaryolarda henüz eksik kalır:

- harici SQL sistemlerine güvenli doğrudan bağlanma ihtiyacı
- çok sıkı query latency ve token budget enforcement
- video veya email tabanlı ingest ihtiyacı

## 15. Hızlı Operasyon Kontrol Listesi

Deploy sonrası minimum kontrol:

1. `docker-compose ps` ile tüm servisler ayakta mı
2. `/health` yeşil mi
3. `POST /collections` başarılı mı
4. küçük bir ingest `indexed` oluyor mu
5. `/query` source-backed sonuç dönüyor mu
6. rate limit `429` veriyor mu
7. worker log'larında tekrar eden failure var mı

Bu yedi adım geçiyorsa servis temel üretim akışında çalışıyor kabul edilebilir.
