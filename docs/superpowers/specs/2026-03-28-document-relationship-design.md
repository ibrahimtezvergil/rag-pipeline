# Document Relationship Design

## Status: COMPLETED

## Goal

Ayni dokuman icindeki ilgili bolumleri birbirine baglamak ve query sonucunda operatore ek baglam gostermek.

## Scope

- chunk seviyesinde `related_chunk_ids`
- ingest sirasinda heuristik relationship olusturma
- query source icinde `related_chunks` metadata dondurme

## Heuristics

- ayni parent chunk altindaki komsu child chunklar
- ayni `section_title` tasiyan yakin chunklar
- maksimum 2 related chunk

## Query Surface

- source item:
  - `related_chunks: [{chunk_id, section_title, snippet}]`

## Safety

- sadece ayni document icinde iliski
- archived chunklar ignore
- relationship yoksa bos liste
