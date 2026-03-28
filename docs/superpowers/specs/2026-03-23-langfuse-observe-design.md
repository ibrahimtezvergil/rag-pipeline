# Langfuse Observe Integration Design

## Status: COMPLETED

## Goal

FastAPI query/chat/ingest akislarina Langfuse trace eklemek; kritik servis cagrilarini child observation olarak izlemek; bunu request akislarini bozmadan ve hassas veri gondermeden yapmak.

## Current State

- `docker-compose.yml` icinde self-hosted Langfuse servisi var.
- Uygulama tarafinda Langfuse SDK entegrasyonu yok.
- Structured JSON loglar var, ancak trace/span korelasyonu yok.
- `QueryService`, `IngestionService`, `llm.py`, `embedder.py`, `reranker.py` agir latency noktalarini olusturuyor.

## Scope

Bu dilim su alanlari kapsar:

- FastAPI agir endpoint'lerinde root trace
  - `POST /query`
  - `POST /chat`
  - `POST /ingest`
  - `POST /ingest/batch`
- Kritik servislerde child observation
  - `QueryService.answer_question`
  - `IngestionService.create_ingestion_job`
  - `llm.generate`
  - `embed_query_text` ve text/image/audio embed akisi
  - `CohereRerankerService.rerank`
- Best-effort, fail-open davranisi

Bu dilim su alanlari kapsamaz:

- `GET /health`, `GET /collections` gibi hafif endpointler
- Prompt/content body capture
- LangGraph node tracing
- Langfuse dashboard kurulum ve score/evaluation entegrasyonu

## Data Safety

Langfuse'a gonderilmeyecek alanlar:

- ham `question`
- tam prompt metni
- chunk/content text'i
- request body
- auth header veya API key

Langfuse metadata olarak gidebilecek guvenli alanlar:

- `tenant_id`
- `application_id`
- `query_hash`
- `retrieval_mode`
- `source_count`
- `document_id`
- `source_type`
- `chunk_count`

## Architecture

### `app/services/tracing.py`

Kucuk bir adapter katmani eklenecek.

Sorumluluklari:

- Langfuse SDK varsa client olusturmak
- SDK yoksa veya config eksikse no-op calismak
- `@observe` dekoratorunu guvenli sekilde expose etmek
- aktif observation'a metadata eklemek icin helper saglamak

API taslagi:

- `observe(*, name: str, as_type: str = "span")`
- `update_current_observation(*, input=None, output=None, metadata=None)`
- `flush_traces()`
- `is_tracing_enabled()`

Implementation notlari:

- `langfuse` import'u lazy/optional olacak
- `capture_input=False`, `capture_output=False` varsayilani ile calisacak
- trace yazimi exception firlatmayacak; helper icinde swallow edilecek

### Endpoint instrumentation

Agir endpoint fonksiyonlari `@observe` ile sarilacak.

- `/query` -> `query-endpoint`
- `/chat` -> `chat-endpoint`
- `/ingest` -> `ingest-endpoint`
- `/ingest/batch` -> `ingest-batch-endpoint`

Endpoint seviyesinde yalnizca guvenli metadata set edilecek.

### Service instrumentation

#### `QueryService.answer_question`

- observation type: `chain`
- metadata:
  - `tenant_id`
  - `application_id`
  - `query_hash`
  - `retrieval_mode`
- cikista:
  - `source_count`
  - `final_retrieval_mode`
  - `confidence_score`

#### `IngestionService.create_ingestion_job`

- observation type: `chain`
- metadata:
  - `tenant_id`
  - `application_id`
  - `document_id`
  - `source_type`
  - `mode`

#### `llm.generate`

- observation type: `generation`
- metadata:
  - `model`
  - `provider=gemini`
- prompt content Langfuse'a verilmez

#### `embedder.py`

- observation type: `embedding`
- metadata:
  - `model`
  - `task_type`
  - `title`
  - `modality`

#### `reranker.py`

- observation type: `retriever`
- metadata:
  - `model`
  - `provider=cohere`
  - `top_n`

## Configuration

`app/config.py` alanlari:

- `langfuse_public_key: str = ""`
- `langfuse_secret_key: str = ""`
- `langfuse_host: str = "http://localhost:3000"`

Tracing enable kosulu:

- public key dolu
- secret key dolu
- optional SDK import basarili

Bu kosullar saglanmazsa tracing no-op olur.

## Error Handling

- Langfuse SDK import edilemezse uygulama acilir, tracing devre disi kalir.
- Langfuse helper icinde olusan hatalar swallow edilir.
- Business logic exception'lari aynen yukari cikar.
- Decorated fonksiyonlarin davranisi tracing yuzunden degismez.

## Testing

### Unit tests

- `tests/test_tracing.py`
  - tracing disabled iken decorator fonksiyonu cagirir
  - tracing enabled iken fake client ile observe wrapper calisir
  - metadata update helper hata yutuyor

### API tests

- `tests/test_api_endpoints.py`
  - `/query`, `/chat`, `/ingest`, `/ingest/batch` endpoint'lerinin tracing decorator ile wrap edildigi path smoke test
  - request body'nin tracing metadata'ya ham haliyle gitmedigi dogrulanir

### Service tests

- `tests/test_query_service.py`
  - `answer_question` query hash ve guvenli metadata ile tracing update cagirir
- `tests/test_ingestion_service.py`
  - ingestion trace metadata `document_id/source_type` tasir
- `tests/test_llm_service.py`
  - generation span metadata `model/provider` tasir
- `tests/test_embedder.py`
  - embedding span metadata `task_type/modality` tasir
- `tests/test_reranker.py`
  - rerank span metadata `top_n/model` tasir
