# Adaptive Chunking Plan

1. Add failing chunking tests for dense/list-like content and narrative content.
2. Add deterministic adaptive window helper to `chunking.py`.
3. Use adaptive per-chunk window inside `_filter_and_split`.
4. Run focused chunking and ingestion regression.
5. Close checklist item.
