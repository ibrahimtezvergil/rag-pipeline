# Document Relationship Plan

1. `RagChunk` icin `related_chunk_ids` alanini ve migration'i ekle.
2. Repository'ye relationship update helper ekle.
3. Ingestion sonrasi chunk relationship heuristigini hesapla ve persist et.
4. Query `_build_sources` icinde related chunk metadata fetch et.
5. Ingestion/query testleri ekle.
6. Checklist satirini ref/akis notuyla kapa.
