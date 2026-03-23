# Qdrant Post-Filtering Fetch Plan

1. Add failing vector store test asserting chunk text is not included in Qdrant payload.
2. Remove `content` from Qdrant upsert payload.
3. Keep query source building on DB chunk fetch path and run regression.
4. Close checklist item.
