# Sync Checkpoints Design

## Goal

Connector bazli ingestion'larda `rag_sync_checkpoints.cursor_state` bilgisini basarili ingest sonunda guncellemek.

## Scope

Bu dilim yalnizca checklist maddesi:

- ``rag_sync_checkpoints`` — connector bazlı cursor_state güncelleme

Kapsam disi:

- `POST /schedules`
- cron tabanli recurring dispatch

## Current State

- `rag_sync_checkpoints` tablosu var ama write path yok.
- `RagDocument` uzerinde `source_connector_id` kolonu var ama ingestion request bu bilgiyi disaridan almiyor.
- successful ingest sonunda connector cursor'i persist edilmiyor.

## Design

### Payload extension

`IngestRequest` iki yeni optional alan alir:

- `source_connector_id: str | None`
- `cursor_state: dict | None`

Bu alanlar document metadata'ya da yazilir.

### Document row

`create_document()` artik optional `source_connector_id` alir ve `rag_documents.source_connector_id` kolonunu doldurur.

### Checkpoint write

`_process_document_job()` basarili completion sonunda:

- `document.source_connector_id` varsa
- checkpoint row upsert edilir

Cursor strategy:

- payload `cursor_state` varsa onu baz al
- uzerine operational metadata merge et:
  - `document_id`
  - `source_ref`
  - `content_hash`

### Repository support

Yeni helper:

- `upsert_sync_checkpoint(source_connector_id, cursor_state)`

Davranis:

- mevcut row varsa update
- yoksa create
- `last_synced_at = now()`

## Failure policy

- Connector id yoksa checkpoint write skip edilir
- Ingest basarisizsa checkpoint update edilmez

## Testing

- create_ingestion_job document row'a `source_connector_id` yazar
- successful sync ingest checkpoint upsert eder
- connector id yoksa checkpoint yazilmaz
