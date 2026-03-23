# Chunk Diff And Reuse Design

## Goal

Ayni source yeniden ingest edildiginde previous version child chunk hash'lerini yeni chunk hash'leriyle karsilastirip:

- unchanged child chunk'larda embed'i skip etmek
- Qdrant'taki mevcut dense vector'u reuse etmek
- `rag_chunk_diff_log` tablosuna `new/modified/deleted/unchanged` kayitlari yazmak

## Scope

Bu dilim birlikte su iki checklist maddesini kapatir:

- `Chunk-level hash karşılaştırma — sadece değişen chunk'lar embed edilir`
- `Diff log yazımı — rag_chunk_diff_log her ingestion'da doldur`

## Current State

- previous versioning var ama her yeni version tum text child chunk'lari yeniden embed ediyor
- `rag_chunk_diff_log` modeli var fakat yazim yok
- previous child chunk metadata'si DB'de var, qdrant point id de DB'de var
- dense vector DB'de yok, ancak Qdrant point id ile fetch edilebilir

## Design

### Previous child snapshot

`_process_document_job()` basinda, `document.previous_document_id` varsa:

- previous document chunk'lari cekilir
- text modality child chunk'lar filtrelenir
- `content_hash -> previous child chunk` map'i kurulur
- ilgili `qdrant_point_id` listesi ile Qdrant'tan dense vector'ler fetch edilir

### Chunk build

`_build_chunk_rows(document, loaded, previous_child_vectors=None)` imzasi genisler.

Text path:

- her raw chunk icin `content_hash` hesaplanir
- hash previous map'te varsa ve vector fetch basariliysa:
  - `embed_text_content` cagrilmaz
  - previous dense vector reuse edilir
  - diff op = `unchanged`
- hash yoksa:
  - normal embed calisir
  - diff op:
    - previous version yoksa `new`
    - previous version varsa `modified`

Deleted:

- previous child hash'lerinden yeni sette olmayanlar icin `deleted` diff row yazilir

### Diff log write

Repository'ye:

- `create_chunk_diff_logs(job_id, entries)`

entries:

- `chunk_id` nullable
- `operation`: `new|modified|unchanged|deleted`

Write timing:

- new/modified/unchanged icin yeni chunk row'lar olustuktan sonra
- deleted icin previous child chunk id ile

### Qdrant vector fetch

`QdrantVectorStore` yeni helper:

- `fetch_dense_vectors(point_ids: list[str]) -> dict[str, list[float]]`

Payload:

- `POST /collections/{collection}/points`
- `{"ids": [...], "with_vector": true, "with_payload": false}`

Failure policy:

- fetch hata verirse fail-open
- ilgili unchanged hash'ler embed fallback'e duser

## Failure policy

- previous vector fetch olmazsa unchanged chunk'lar yeniden embed edilir
- diff log yazimi hata verirse ingestion fail olmamali demek riskli; bu dilimde repository write business path'in parcasi, hata propagation normal kalir

## Testing

- unchanged child chunk dense vector reuse edilir, `embed_text_content` cagrilmaz
- changed/new child chunk embed edilir
- deleted previous chunk icin `deleted` diff log yazilir
- previous vector fetch hata verirse embed fallback olur
