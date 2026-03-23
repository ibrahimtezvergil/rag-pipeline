# Semantic Deduplication Plan

1. Add failing tests for Qdrant duplicate lookup and ingestion chunk skip.
2. Add duplicate lookup method to `QdrantVectorStore`.
3. Add ingestion duplicate check before vector chunk row creation.
4. Add threshold config.
5. Run focused regression and close checklist item.
