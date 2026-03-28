# Feedback Loop Design

## Status: COMPLETED

## Goal

Gercek kullanici geri bildirimini toplamak ve negatif sinyali retrieval sonucuna yansitmak.

## Scope

- `POST /feedback`
- `rating=up|down`
- `chunk_ids[]`
- opsiyonel `note`, `query_hash`
- feedback kaydi PostgreSQL
- negatif feedback alan chunk'lar query final source siralamasinda dusurulur

## Data Model

- `rag_chunk_feedback`
  - `id`
  - `tenant_id`
  - `application_id`
  - `document_id`
  - `chunk_id`
  - `rating`
  - `note`
  - `query_hash`
  - `created_at`

## API

- `POST /feedback`
  - request:
    - `rating`
    - `chunk_ids`
    - `note?`
    - `query_hash?`
  - response:
    - `status=recorded`
    - `rating`
    - `recorded_count`

## Query Impact

- Query response zaten source bazinda `chunk_id` tasir.
- Query pipeline final source listesi icin feedback aggregate toplar.
- `down > up` olan chunk'lar score penalty alir ve sirada geriye duser.
- `up > down` olan chunk'lar hafif pozitif bias alabilir.

## Safety

- feedback kaydi query cevabini bozmaz
- application disi chunk id verilirse `400`
- feedback etkisi sadece ayni application icinde uygulanir
