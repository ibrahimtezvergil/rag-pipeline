# Qdrant Post-Filtering Fetch Design

## Goal

Qdrant payload'ında metin taşımamak; vector search sonrası snippet ve parent context'i PostgreSQL chunk kayıtlarından üretmek.

## Scope

- `app/services/vector_store.py` payload küçültme
- retrieval sonrası DB chunk fetch mevcut akışını koruma
- regresyon testleri

## Flow

1. Ingestion sırasında Qdrant'a sadece `document_id`, `chunk_id` ve filtre metadata'sı yazılır.
2. Query Qdrant'tan sadece ranked `chunk_id`/`document_id`/score alır.
3. Query service bu `chunk_id` listesini PostgreSQL'den fetch eder.
4. `snippet` ve `parent_context` DB chunk `content` alanından kurulur.

## Notes

- Bu değişiklik yeni ingest edilen point'ler için geçerlidir.
- Legacy Qdrant payload'da `content` kalsa bile query tarafı artık buna ihtiyaç duymaz.
