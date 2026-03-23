# Production Smoke Blockers Design

## Goal

`docker-compose up` ile ayağa kalkamayan ve canlı PDF ingest/query smoke testini bozan blocker'ları tek dilimde kapatmak.

## Current State

- `api/worker` image build'i `httpx==0.27.0` ve `crawl4ai==0.6.3` bağımlılık çakışmasıyla kırılıyor.
- `pgbouncer` container root olarak başladığı için hemen exit ediyor.
- `langfuse` aynı `ragdb` üstünde Prisma `P3005` ile exit ediyor.
- Alembic'te iki head var: `002_add_rag_schedules`, `003_add_chunk_content`.
- `CollectionsService` unnamed dense vector oluşturuyor; `QdrantVectorStore` named `dense` vector bekliyor.
- `ensure_collection()` mevcut collection'da `409`'u hata sayıyor.
- Live Qdrant `v1.13.4` ile `/collections/{name}/points/query` yolu çalışmıyor; ingestion/query bu yüzden kırılıyor.
- Sync ingest hata yolunda `rag_documents.status=indexing`, `rag_ingestion_jobs.status=running` kalabiliyor.

## Scope

Bu dilim yalnızca deploy ve smoke-test blocker'larını kapatır:

- dependency resolution
- compose infra startup
- alembic graph
- Qdrant collection/query contract
- sync ingest failure finalization

Kapsam dışı:

- DB loader implementasyonu
- latency/token budget enforcement
- Langfuse dashboard veya prod tuning

## Design

### 1. Dependency and Compose

- `requirements.txt` içindeki `httpx` sürümü `crawl4ai` ile uyumlu olacak şekilde yükseltilir.
- `pgbouncer` image non-root user ile çalıştırılır.
- `langfuse` varsayılan compose akışında app DB'den ayrılır:
  - ayrı `langfuse_db` Postgres servisi kullanılır.
  - böylece `ragdb` şeması ile Prisma migration çakışmaz.

### 2. Alembic Graph

- Yeni merge revision eklenir.
- `alembic upgrade head` tek head üzerinden çalışır.

### 3. Qdrant Contract

- `CollectionsService.create_collection()` ile `QdrantVectorStore.ensure_collection()` aynı named-vector payload'ı kullanır:
  - `vectors.dense`
  - `sparse_vectors.sparse`
- `ensure_collection()` idempotent olur:
  - mevcut collection ve uyumlu config varsa no-op
  - mevcut collection uyumsuzsa açık hata üretir
- Search/dedup path'i Qdrant 1.13 ile uyumlu endpoint formatına çekilir.
  - Aynı endpoint dense/sparse/search/dedup için ortak helper üzerinden çalışır.

### 4. Sync Ingest Failure Finalization

- `create_ingestion_job(... mode=sync)` içinde `_process_document_job()` exception fırlatırsa:
  - document status `failed`
  - job status `failed`
  - `error_message` yazılır
  - transaction commit edilir
  - HTTP tarafı 500 dönebilir, ama DB state yarım kalmaz

## Success Criteria

- `docker-compose up -d` build/start eder.
- `docker-compose ps` içinde `api`, `worker`, `pgbouncer`, `langfuse` ayakta görünür.
- `alembic upgrade head` başarılı olur.
- `/health` 200 ve tüm servisler `up`.
- Canlı sync PDF ingest başarılı olur ve `GET /ingest/{id}` `indexed` döner.
- `/query` source-backed response döner.
- Rate-limit davranışı bozulmaz.

## Testing

- Unit:
  - dependency/config tests
  - compose/deployment tests
  - Qdrant collection payload/idempotency tests
  - sync ingest failure finalization test
- Verification:
  - focused pytest suite
  - `docker-compose up -d`
  - `docker-compose ps`
  - live `/health`, `/ingest`, `/query`, rate-limit smoke
