# Observability Logging Design

## Goal

RAG servisinin ingestion ve query akışlarına production-ready structured JSON logging eklemek. Hedef, uygulama stdout'una makine tarafından toplanabilir log event'leri yazmak ve özellikle ingestion/query performansını, retrieval sonucunu ve hata anlarını kör bırakmamaktır.

## Scope

Bu dilimde sadece structured stdout logging tamamlanır.

Kapsam içi:
- ingestion JSON event log
- query JSON event log
- ham query yerine SHA256 query hash
- temel latency alanları

Kapsam dışı:
- Langfuse trace/span
- dashboard kurulumları
- ayrı telemetry DB/Redis sink
- alerting

## Current State

- Checklist'te observability maddeleri açık.
- Kod tabanında ingestion/query için standartlaştırılmış structured logger yok.
- `ingestion.py` toplam `duration_ms`'i `rag_ingestion_jobs` tablosuna yazıyor ama chunk bazlı structured log yok.
- Query, rerank ve LLM akışlarında süre ölçümü response içinde değil; log tarafında da kaydedilmiyor.
- `llm_ms` alanı direkt query pipeline implement edildiğinde doldurulur; o iş tamamlandığından bu dilimde `llm_ms` artık ölçülebilir.

## Recommended Approach

Stdout'a yazan hafif bir JSON logger helper eklemek.

Neden:
- Docker/Dokploy/Loki/Datadog ile uyumlu en düşük sürtünmeli yol bu.
- Uygulamaya ikinci bir telemetry storage bağımlılığı eklemez.
- Sonraki `Langfuse` ve dashboard işleri için temiz temel sağlar.

**Logger kütüphanesi:** Yeni bağımlılık eklenmez. Python standart `logging` modülü kullanılır; `observability.py` JSON payload'u `json.dumps` ile serialize edip `logger.info(json_str)` olarak yazar. `structlog` bu dilimde kapsam dışıdır.

## Event Model

İlk sürümde iki event tipi yazılır:
- `ingestion.chunk_indexed`
- `query.completed`

Ortak alanlar:
- `event`
- `timestamp`
- `tenant_id`
- `project_id`

`ingestion.chunk_indexed` alanları:
- `document_id`
- `chunk_id`
- `chunk_index`
- `modality`
- `embed_ms`
- `token_count` — char-based tahmin (`len(content) // 4`); tiktoken bu dilimde kapsam dışı, alan nullable
- `vector_dimension`

**Event frekansı:** `ingestion.chunk_indexed` her chunk için ayrı ayrı emit edilir (per-chunk). 50 chunk'lı bir dokümanda 50 event üretilir.

`query.completed` alanları:
- `query_hash`
- `retrieval_mode`
- `reranker_ms`
- `llm_ms` — direkt query pipeline tamamlandığından doldurulabilir; key her zaman yazılır, LLM çağrısı yoksa `null`
- `top_chunk_score`
- `source_count`

## Privacy Rule

Ham query içeriği loglanmaz.

Yerine:
- `sha256(question + tenant_id + project_id)` ya da eşdeğer deterministic hash yazılır

Bu sayede:
- tekrar eden sorgular ilişkilendirilebilir
- kullanıcı verisi düz metin olarak log'a düşmez

## Service Boundaries

- `app/services/observability.py`
  JSON log helper burada tutulur.
- `app/services/ingestion.py`
  Chunk indexleme sonrası `ingestion.chunk_indexed` event'i üretir.
- `app/services/query.py`
  Query tamamlandığında `query.completed` event'i üretir.

Logger helper şu sorumlulukları üstlenir:
- payload birleştirme
- JSON serialization
- standart logger üstünden `info` yazma

## Timing Strategy

İlk sürümde coarse timing yeterlidir:
- `embed_ms`
- `reranker_ms`
- `llm_ms`

Süreler `time.perf_counter()` ile ölçülür.

Timing yoksa:
- alan `null` olabilir
- ama key kaybolmaz

## Error Handling

- Log yazımı ana request/worker akışını kırmamalı.
- JSON serialization başarısız olursa güvenli fallback ile boş/normalize payload loglanmalı.
- `query.completed` event'i, LLM fallback yolunda da yazılmalı.

## Testing

- `observability.py` JSON payload testi
- query hash deterministic testi
- query completed log'unda `query_hash`, `llm_ms`, `reranker_ms`, `top_chunk_score` alanları testi
- ingestion chunk log'unda `chunk_index`, `modality`, `embed_ms`, `token_count` alanları testi

## Rollout

Bu dilim sonunda:
- checklist'te şu üç madde kapanır:
  - `Structured JSON log — ingestion`
  - `Structured JSON log — query`
  - `Query içeriği loglanmaz — sadece SHA256 hash (GDPR)`
- sonraki observability işleri `Langfuse` ve dashboard tarafına geçebilir
