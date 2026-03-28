# Web, Image, Audio Loaders Implementation Plan

## Status: ARCHIVED — SUPERSEDED

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add checklist-level `web`, `image`, and `audio` source loaders to `rag-service`, including crawl4ai-backed web ingestion, Gemini native image embedding, and 120-second audio clip ingestion.

**Architecture:** Keep `app/services/loaders.py` as the single loader entry point, but move reusable media preparation into a focused helper module. `web` stays text-first and feeds the existing chunk/text embed pipeline; `image` and `audio` use Gemini native multimodal paths through `app/services/embedder.py`, while `audio` adds clip orchestration in ingestion/worker flow. Existing query/vector-store behavior remains unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, httpx, crawl4ai, Gemini REST APIs, PyMuPDF (existing), pytest

---

## File Structure

- Modify: `rag-service/app/schemas/ingest.py`
  Purpose: extend `source_type` validation and payload rules for `image` and `audio`, including URL/base64/file-name variants.
- Modify: `rag-service/app/services/loaders.py`
  Purpose: keep loader dispatch, add checklist-level `web`, `image`, and `audio` loader paths.
- Create: `rag-service/app/services/media.py`
  Purpose: shared helpers for mime sniffing, base64 decoding, temp file creation, duration probing, and 120-second clip window generation.
- Modify: `rag-service/app/services/embedder.py`
  Purpose: add Gemini native image/audio request builders and response parsing.
- Modify: `rag-service/app/services/ingestion.py`
  Purpose: wire new loader outputs into sync/async ingestion, especially audio clip chunk rows and image direct-embed metadata.
- Modify: `rag-service/app/services/vector_store.py`
  Purpose: only if payload needs modality-specific metadata for image/audio chunk rows.
- Modify: `rag-service/app/config.py`
  Purpose: add crawl4ai and media-related settings only if they are required for runtime behavior.
- Create: `rag-service/migrations/versions/004_add_chunk_media_metadata.py`
  Purpose: only if existing chunk/document metadata columns are insufficient; prefer metadata-first unless a real schema gap appears.
- Modify: `rag-service/tests/test_loaders.py`
  Purpose: loader contract tests for crawl4ai web, image, and audio.
- Modify: `rag-service/tests/test_embedder.py`
  Purpose: Gemini image/audio payload tests.
- Modify: `rag-service/tests/test_ingestion_service.py`
  Purpose: sync/worker ingestion tests for image/audio/web.
- Modify: `rag-service/tests/test_ingest.py`
  Purpose: API payload acceptance tests for `source_type=image|audio`.
- Modify: `rag_service_checklist_v3.md`
  Purpose: close `web`, `image`, and `audio` loader checklist lines only after verification.

## Chunk 1: Web Loader

### Task 1: Extend ingest schema for image/audio source types before loader work

**Files:**
- Modify: `rag-service/app/schemas/ingest.py`
- Test: `rag-service/tests/test_ingest.py`

- [ ] **Step 1: Write the failing API tests**

Add tests that prove `POST /ingest` accepts `source_type="image"` and `source_type="audio"` with the same URL/base64 conventions already used by `pdf`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py`
Expected: FAIL because schema rejects or mishandles `image` / `audio`.

- [ ] **Step 3: Write minimal schema changes**

Update the source type literal and validation logic so `image` and `audio` are valid, while keeping the single-source-input rule intact.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py`
Expected: PASS for the new payload cases.

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/schemas/ingest.py rag-service/tests/test_ingest.py
git commit -m "feat: accept image and audio ingest payloads"
```

### Task 2: Add failing tests for checklist-level web loader behavior

**Files:**
- Modify: `rag-service/tests/test_loaders.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing loader tests**

Add tests for:
- crawl4ai-rendered HTML path
- fallback static HTML path when crawl4ai fails
- nav/footer removal in the final extracted text
- `loader_strategy` metadata being `crawl4ai_rendered` or `static_html_fallback`

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_ingestion_service.py`
Expected: FAIL because loader dispatch still uses only `httpx` stripping.

- [ ] **Step 3: Write minimal web loader implementation**

Add a crawl4ai-backed web path in `app/services/loaders.py`. Preserve the current `httpx` path as fallback and standardize cleaned output metadata.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_ingestion_service.py`
Expected: PASS for new web tests.

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/loaders.py rag-service/tests/test_loaders.py rag-service/tests/test_ingestion_service.py
git commit -m "feat: add crawl4ai-backed web loader"
```

## Chunk 2: Image Loader

### Task 3: Add failing tests for Gemini native image loader

**Files:**
- Create: `rag-service/app/services/media.py`
- Modify: `rag-service/tests/test_loaders.py`
- Modify: `rag-service/tests/test_embedder.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- image URL loading
- image base64 loading
- mime detection / filename behavior
- Gemini image embed payload construction
- ingestion metadata showing `loader_strategy="gemini_direct_image"`

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_embedder.py tests/test_ingestion_service.py`
Expected: FAIL because image load/embed paths do not exist.

- [ ] **Step 3: Write minimal image implementation**

Implement:
- shared image prep helpers in `app/services/media.py`
- `load_image_source(...)` in `app/services/loaders.py`
- Gemini native image embedding helper in `app/services/embedder.py`
- ingestion wiring so sync/async image ingestion stores direct-embed metadata and vector rows

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_embedder.py tests/test_ingestion_service.py`
Expected: PASS for image tests.

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/media.py rag-service/app/services/loaders.py rag-service/app/services/embedder.py rag-service/app/services/ingestion.py rag-service/tests/test_loaders.py rag-service/tests/test_embedder.py rag-service/tests/test_ingestion_service.py
git commit -m "feat: add native Gemini image loader"
```

## Chunk 3: Audio Loader

### Task 4: Add failing tests for 120-second audio clip ingestion

**Files:**
- Create: `rag-service/app/services/media.py`
- Modify: `rag-service/tests/test_loaders.py`
- Modify: `rag-service/tests/test_embedder.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:
- short audio -> single clip
- long audio -> deterministic 120s clip windows
- loader metadata includes duration, clip count, clip ranges
- Gemini audio embed payload is built per clip
- async worker path records audio clip chunk rows

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_embedder.py tests/test_ingestion_service.py`
Expected: FAIL because audio clip split and native embedding do not exist.

- [ ] **Step 3: Write minimal audio implementation**

Implement:
- duration probe and clip-window helper in `app/services/media.py`
- `load_audio_source(...)` in `app/services/loaders.py`
- Gemini native audio embedding helper in `app/services/embedder.py`
- ingestion/worker handling so each clip becomes a retrieval row with modality-aware metadata

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv313/bin/python -m pytest -q tests/test_loaders.py tests/test_embedder.py tests/test_ingestion_service.py`
Expected: PASS for audio tests.

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/media.py rag-service/app/services/loaders.py rag-service/app/services/embedder.py rag-service/app/services/ingestion.py rag-service/tests/test_loaders.py rag-service/tests/test_embedder.py rag-service/tests/test_ingestion_service.py
git commit -m "feat: add clipped audio loader"
```

## Chunk 4: Checklist Closure and Final Verification

### Task 5: Close checklist items only after full verification

**Files:**
- Modify: `rag_service_checklist_v3.md`

- [ ] **Step 1: Update checklist wording if needed**

Make the loader lines match the actual implementation:
- `Web loader — crawl4ai (JS render, nav/footer temizleme)`
- `Audio loader — Gemini Embedding 2 native embed (120s clip'lere böl)`
- `Image loader — Gemini Embedding 2 direkt embed (PNG, JPEG, max 6/request)`

- [ ] **Step 2: Mark only completed lines**

Check the three loader boxes only if the implementation and tests genuinely satisfy the checklist wording.

- [ ] **Step 3: Run targeted verification**

Run: `.venv313/bin/python -m pytest -q tests/test_ingest.py tests/test_loaders.py tests/test_embedder.py tests/test_ingestion_service.py`
Expected: PASS

- [ ] **Step 4: Run full verification**

Run: `.venv313/bin/python -m pytest -q`
Expected: PASS with no failures

- [ ] **Step 5: Commit**

```bash
git add rag_service_checklist_v3.md rag-service/app rag-service/tests rag-service/migrations
git commit -m "feat: complete web image audio loaders"
```
