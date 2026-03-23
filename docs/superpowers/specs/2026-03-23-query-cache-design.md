# Query Cache Design

## Goal

`/query` ve dolayli `/chat` akislarina production-ready Redis query cache eklemek; veri degisince cache'i invalidate etmek; bunu fail-open ve request semantics bozulmadan yapmak.

## Scope

Bu dilim birlikte su iki checklist maddesini kapatir:

- `Query cache — sha256(query + tenant_id + scope_id) -> Redis TTL 1 saat`
- `Cache invalidation — collection re-index edilince`

## Current State

- Redis zaten `chat` memory ve `rate limiting` icin kullaniliyor.
- Query cevabi her istekte yeniden retrieve/rerank/generate yapiyor.
- Ingestion basarili tamamlandiginda veya delete oldugunda query cache invalidation yok.
- Query request shape'i retrieval sonucu etkileyen birden fazla alan tasiyor:
  `retrieval_mode`, `collections`, `merge_strategy`, `exclude_*`, `acl`, `scope_*`, `entity_id`, `snapshot_date`, `tags`

## Design

### Cache boundary

Cache, `QueryService.answer_question()` seviyesinde uygulanacak.

Akis:

1. project yuklenir
2. cache key hesaplanir
3. cache hit ise serialized response dondurulur
4. miss ise mevcut query pipeline calisir
5. final response Redis'e yazilir

`/chat` dogrudan ek entegrasyon gerektirmez; zaten `QueryService` kullandigi icin ayni cache'den faydalanir.

### Cache key

Checklist'teki basit tarif korunur, ama production dogrulugu icin cache key su guvenli fingerprint'ten uretilir:

- original `question`
- `tenant_id`
- `project_id`
- `retrieval_mode`
- `collections`
- `merge_strategy`
- `exclude_sources`
- `exclude_documents`
- `acl`
- `scope_type`
- `scope_id`
- `entity_id`
- `snapshot_date`
- `tags`

Key formati:

- data key: `query_cache:item:{sha256(...)}`
- project index key: `query_cache:index:{project_id}`

Index set'i invalidation icin kullanilir.

### TTL

- Varsayilan TTL: `3600` saniye
- Config: `query_cache_ttl_seconds`

### Serialization

Stored payload:

- final `answer_question()` response body
- raw prompt/question/content degil

JSON serialize edilir. Fail-open geregi deserialize hatasinda miss kabul edilir.

### Invalidation

Project seviyesinde invalidation yapilacak.

Tetik noktalar:

- `IngestionService._process_document_job()` basarili tamamlandiginda
- `IngestionService.delete_ingestion_job()` basarili tamamlandiginda

Davranis:

- `query_cache:index:{project_id}` set'i okunur
- tum item key'leri silinir
- index key silinir

Bu ilk surumde collection-level degil project-level invalidation yapar. Mevcut ingestion akisi collection secimi tasimadigi icin bu en dogru ve guvenli sinirdir.

## Failure policy

- Redis down ise cache fail-open:
  - query normal devam eder
  - write/invalidate hata verirse swallow edilir
- Cache hit yoksa davranis degismez
- Cache hicbir business exception uretmez

## Observability

Structured log veya response yuzeyi degismeyecek.

Tracing metadata'ya opsiyonel guvenli alan eklenebilir:

- `cache_hit: true/false`

Bu dilimde yeterli.

## Files

- Create: `rag-service/app/services/query_cache.py`
- Modify: `rag-service/app/config.py`
- Modify: `rag-service/app/services/query.py`
- Modify: `rag-service/app/services/ingestion.py`
- Test: `rag-service/tests/test_query_cache.py`
- Modify: `rag-service/tests/test_query_service.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

## Testing

### Unit

- cache key deterministik
- hit path serialized response dondurur
- miss path store eder
- Redis hata verirse fail-open
- invalidation project index uzerinden item key'lerini siler

### Query service

- cache hit durumunda `embed_query_text` cagrilmaz
- cache miss durumunda response write edilir
- cached response ayni schema shape'i ile doner

### Ingestion

- basarili process sonunda project cache invalidate edilir
- delete sonunda project cache invalidate edilir
