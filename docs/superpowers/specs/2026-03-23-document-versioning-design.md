# Document Versioning Design

## Status: COMPLETED

## Goal

Ayni `project_id + source_ref` icin tekrar ingestion geldiginde yeni bir `RagDocument` version olusturmak, onceki aktif versiyonu supersede etmek ve retrieval'in yalnizca guncel versiyonu gormesini saglamak.

## Scope

Bu dilim yalnizca checklist maddesi:

- `Document versioning — version++, previous_document_id`

Kapsam disi:

- `Chunk-level hash karşılaştırma`
- `Diff log yazımı`
- `Scheduled re-index`
- `rag_sync_checkpoints`

## Current State

- `rag_documents` tablosunda `version` ve `previous_document_id` kolonlari var.
- Ancak `create_ingestion_job()` her zaman `version=1` gibi yeni document row aciyor.
- Query katmani `status == indexed` olan tum document'lari goruyor; ayni source icin yeni ingestion gelirse eski versiyon da retrieval'e karisabilir.

## Design

### New document creation

`create_ingestion_job()` once ayni `project_id + source_ref` icin en son aktif document'i arar.

- eski aktif document yoksa:
  - `version = 1`
  - `previous_document_id = None`
- varsa:
  - `version = previous.version + 1`
  - `previous_document_id = previous.id`

### Supersede flow

Yeni document basariyla `indexed` olduktan sonra:

- previous document `status = superseded`
- previous document chunk'lari `is_archived = True`
- previous qdrant point'leri silinir

Boylece:

- async ingest sirasinda eski version bir sure daha servis verebilir
- yeni version tamamlandigi anda retrieval yalnizca yeni row'u gorur

### Repository changes

Gerekli repository API'leri:

- `get_latest_document_by_source_ref(project_id, source_ref)`
- `supersede_document(document)`

`create_document()` optional olarak `version` ve `previous_document_id` alir.

## Failure policy

- Yeni version indexing basarisiz olursa eski indexed version yerinde kalir.
- Supersede adimi yalnizca yeni version indexing tamamlandiktan sonra calisir.

## Testing

- create job ikinci kez cagrildiginda `version++` ve `previous_document_id` set edilir
- basarili indexing sonrasi onceki version supersede olur
- onceki qdrant point'leri silinir
- failure durumunda onceki version indexed kalir
