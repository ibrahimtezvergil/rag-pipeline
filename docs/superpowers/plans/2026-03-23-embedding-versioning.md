# Embedding Versioning Plan

## Status: COMPLETED

1. Add failing tests for stale document requeue and current-version skip.
2. Add repository query for latest indexed documents and their child chunks.
3. Implement `IngestionService.requeue_stale_documents()` with current embed version detection and async requeue.
4. Add ARQ worker tick for periodic stale scan.
5. Run focused regression and close checklist item.
