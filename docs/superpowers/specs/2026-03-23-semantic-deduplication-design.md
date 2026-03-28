# Semantic Deduplication Design

## Status: COMPLETED

## Goal

Text child chunk embedding'i mevcut tenant/scope corpus'una semantik olarak çok yakınsa (`score >= 0.97`) yeni vector point yazmamak.

## Scope

- Qdrant nearest-neighbor duplicate lookup
- ingestion text child path'inde semantic dedup kontrolü
- config threshold

## Flow

1. Yeni text chunk embed edilir.
2. Qdrant `points/query` ile tenant/scope filtreli en yakın dense komşu aranır.
3. Score threshold üstündeyse chunk duplicate kabul edilir.
4. Duplicate chunk parent/child pair olarak persist edilmez, vector upsert'e girmez.
5. Diğer chunk'lar normal ingest akışına devam eder.

## Notes

- İlk sürüm sadece text child chunk'larda çalışır.
- Aynı ingest içindeki hash-reuse mantığından ayrıdır; corpus-genel semantik benzerliği hedefler.
