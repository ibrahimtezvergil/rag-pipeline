# Audio Retrieval Accuracy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve audio ingestion so each indexed vector represents the correct time window and transcript-aligned chunk text materially improves RAG retrieval quality.

**Architecture:** Extend the existing `audio -> loader -> ingestion -> embedder` pipeline instead of replacing it. Add reliable duration probing and real audio slicing in the media layer, add a concrete local Whisper-backed transcript provider with normalized metadata output, and have ingestion create clip-scoped audio vectors plus transcript-derived text vectors when available.

**Tech Stack:** FastAPI service layer, existing ingestion pipeline, Gemini embedding API, ffmpeg/ffprobe, pytest, SQLAlchemy async

---

## Chunk 1: Media Foundations

### Task 1: Add failing tests and implementation for duration probing and clip slicing

**Files:**
- Modify: `rag-service/tests/test_loaders.py`
- Create: `rag-service/tests/test_media.py`

- [x] **Step 1: Write the failing test**

```python
def test_probe_audio_duration_seconds_uses_ffprobe_output(monkeypatch):
    monkeypatch.setattr(media_module, "_probe_media_duration_with_ffprobe", lambda *_args, **_kwargs: 255.4)
    assert media_module.probe_audio_duration_seconds(b"ID3voice", "voice.mp3") == 255


def test_slice_audio_clip_bytes_returns_distinct_ranges(monkeypatch):
    calls = []

    def fake_slice(binary, filename, start_second, end_second):
        calls.append((start_second, end_second))
        return f"{start_second}-{end_second}".encode()

    monkeypatch.setattr(media_module, "_slice_audio_with_ffmpeg", fake_slice)

    clips = media_module.slice_audio_clip_bytes(
        b"ID3voice",
        "voice.mp3",
        [
            {"clip_index": 0, "start_second": 0, "end_second": 120},
            {"clip_index": 1, "start_second": 120, "end_second": 240},
        ],
    )

    assert [clip["audio_bytes"] for clip in clips] == [b"0-120", b"120-240"]
    assert calls == [(0, 120), (120, 240)]
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_media.py tests/test_loaders.py -k "audio or media"`
Expected: FAIL because ffprobe-backed duration and clip slicing helpers do not exist yet.

- [x] **Step 3: Write minimal implementation**

```python
def probe_audio_duration_seconds(binary: bytes, filename: str | None = None) -> int:
    duration = _probe_media_duration_with_ffprobe(binary, filename)
    if duration is not None:
        return max(1, int(duration))
    return _legacy_duration_fallback(binary, filename)


def slice_audio_clip_bytes(binary: bytes, filename: str | None, clips: list[dict[str, int]]) -> list[dict[str, object]]:
    output = []
    for clip in clips:
        output.append(
            {
                **clip,
                "audio_bytes": _slice_audio_with_ffmpeg(
                    binary,
                    filename,
                    int(clip["start_second"]),
                    int(clip["end_second"]),
                ),
            }
        )
    return output
```

Implementation notes:
- Implement `_probe_media_duration_with_ffprobe(...)` with `subprocess.run(...)`.
- Write `binary` to a `NamedTemporaryFile`, because probing a real file is more portable than streaming arbitrary compressed audio into `ffprobe`.
- Run `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 <tempfile>`.
- Parse stdout as `float`; return `None` on non-zero exit, parse error, or missing binary.
- Implement `_slice_audio_with_ffmpeg(...)` with `subprocess.run(...)` against the same temp-file pattern.
- Run `ffmpeg -ss <start> -to <end> -i <tempfile> -c copy <clipfile>` first; if stream copy fails, retry with a lightweight transcode path appropriate for the source format.
- Read the resulting clip bytes from the output temp file and remove temp files in `finally`.
- Treat missing `ffmpeg`/`ffprobe` or command failure as soft failure in the media layer by returning `None` for duration probe and raising a typed slicing exception that ingestion can catch.

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_media.py tests/test_loaders.py -k "audio or media"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/tests/test_media.py rag-service/tests/test_loaders.py rag-service/app/services/media.py
git commit -m "test: add audio media foundations"
```

## Chunk 2: Transcript Provider and Normalization

### Task 3: Add failing tests for audio metadata normalization and fallback

**Files:**
- Modify: `rag-service/tests/test_audio_metadata.py`
- Modify: `rag-service/app/services/audio_metadata.py`

- [x] **Step 1: Write the failing test**

```python
async def test_extract_audio_metadata_normalizes_provider_segments(monkeypatch):
    async def fake_provider(_audio_bytes, *, filename=None):
        return {
            "text": "Merhaba dunya",
            "segments": [
                {"start": 0.0, "end": 4.8, "text": "Merhaba dunya", "avg_logprob": -0.1}
            ],
        }

    monkeypatch.setattr(audio_metadata_module, "_run_transcription_provider", fake_provider)

    result = await audio_metadata_module.extract_audio_metadata(b"ID3voice", filename="voice.mp3")

    assert result["status"] == "ok"
    assert result["transcript"] == "Merhaba dunya"
    assert result["segments"][0]["start_second"] == 0
    assert result["segments"][0]["end_second"] == 4
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_audio_metadata.py`
Expected: FAIL because the service currently always returns `unavailable`.

- [x] **Step 3: Write minimal implementation**

```python
settings = get_settings()
if not settings.audio_metadata_enabled:
    return disabled_audio_metadata()

provider_result = await _run_transcription_provider(audio_bytes, filename=filename)
return normalize_audio_metadata(provider_result)
```

Provider decision:
- Use a local Whisper-style provider in-process for the first implementation.
- Introduce `_run_transcription_provider(...)` as a small internal seam that currently dispatches to `_run_local_whisper_transcription(...)`.
- Use `faster-whisper` for the first implementation, not `openai-whisper`, to keep local CPU/GPU execution practical in the existing service process.
- Do not plan OpenAI Whisper API or Gemini transcription in this iteration; keep the contract provider-agnostic so those can be added later without changing ingestion.

Behavior requirements:
- Preserve the existing `audio_metadata_enabled` early-return contract exactly.
- If the local Whisper dependency is unavailable, return `status="unavailable"` instead of failing ingestion.
- Normalize provider output into `transcript` plus `segments[{start_second, end_second, text, confidence, speaker_label}]`.
- Add the dependency explicitly in the Python requirements file used by `rag-service` and cover the import-missing path in `tests/test_audio_metadata.py`.

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_audio_metadata.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/audio_metadata.py rag-service/tests/test_audio_metadata.py
git commit -m "feat: normalize audio transcript metadata"
```

## Chunk 3: Ingestion Correctness

### Task 4: Add failing tests proving each clip embeds only its own bytes

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/tests/test_ingestion_service.py`

- [x] **Step 1: Write the failing test**

```python
async def test_run_ingest_job_embeds_each_audio_clip_with_clip_scoped_bytes(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[
            {"clip_index": 0, "start_second": 0, "end_second": 120},
            {"clip_index": 1, "start_second": 120, "end_second": 240},
        ],
        audio_metadata={"status": "unavailable", "provider": "disabled", "transcript": None, "segments": []},
    )
    embedded_payloads = []

    async def fake_embed_audio(*, audio_bytes, title, mime_type):
        embedded_payloads.append(audio_bytes)
        return {"values": [0.1, 0.2], "model": "test", "embed_version": "test-2", "dimension": 2}

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio)
    monkeypatch.setattr(
        ingestion_service_module,
        "slice_audio_clip_bytes",
        lambda _binary, _filename, clips: [
            {**clips[0], "audio_bytes": b"clip-a"},
            {**clips[1], "audio_bytes": b"clip-b"},
        ],
    )

    await service._build_chunk_rows(document, loaded)

    assert embedded_payloads == [b"clip-a", b"clip-b"]
```

Fixture requirements:
- Add explicit helpers in `rag-service/tests/test_worker_ingest.py` such as `build_audio_document(...)` and `build_loaded_audio_payload(...)`.
- `build_loaded_audio_payload(...)` should return the same shape as `load_audio_source(...)`: `content`, `audio_bytes`, and `metadata` with `title`, `mime_type`, `clips`, and `audio_metadata`.
- Do not rely on implicit defaults from unrelated fixtures; each audio retrieval test must state its clip windows and transcript metadata inline or through a dedicated helper.

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k clip_scoped`
Expected: FAIL because ingestion currently sends the full file bytes for every clip.

- [x] **Step 3: Write minimal implementation**

```python
clip_payloads = slice_audio_clip_bytes(audio_bytes, title, list(metadata.get("clips") or []))
for clip_payload in clip_payloads:
    embedding = await embed_audio_content(
        audio_bytes=clip_payload["audio_bytes"],
        title=clip_label,
        mime_type=mime_type,
    )
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k clip_scoped`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/tests/test_worker_ingest.py rag-service/tests/test_ingestion_service.py rag-service/app/services/ingestion.py rag-service/app/services/media.py
git commit -m "fix: embed clip-scoped audio bytes"
```

### Task 5: Add failing tests for transcript-aligned text vectors

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/app/services/ingestion.py`

- [x] **Step 1: Write the failing test**

```python
async def test_run_ingest_job_creates_text_vector_for_transcript_backed_audio_clip(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}],
        audio_metadata={
            "status": "ok",
            "provider": "whisper",
            "transcript": "segment text",
            "segments": [
                {"start_second": 10, "end_second": 18, "text": "segment text", "confidence": 0.91, "speaker_label": None}
            ],
        },
    )

    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        return {"values": [0.3, 0.4], "model": "text-model", "embed_version": "text-2", "dimension": 2}

    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text)

    rows, vector_indices, _diff = await service._build_chunk_rows(document, loaded)

    assert any(row["modality"] == "text" and row["content"] == "segment text" for row in rows)
    assert len(vector_indices) >= 2
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k transcript_backed_audio`
Expected: FAIL because ingestion currently stores only audio child vectors.

- [x] **Step 3: Write minimal implementation**

```python
transcript_content = clip_summary
if transcript_content.strip() and transcript_content != fallback_label:
    transcript_embedding = await embed_text_content(transcript_content, clip_label)
    chunk_rows.append(...)
```

Content rule:
- `clip_summary` is the canonical chunk text for audio clips.
- When transcript segments overlap the clip window, `clip_summary` must be built from those segment texts.
- When no transcript text overlaps, `clip_summary` must equal the fallback label: `<title> clip N (start-end s)`.
- The text vector child chunk should be created only for transcript-derived `clip_summary`, never for the fallback label.
- The Task 5 fixture must include at least one transcript segment fully inside the clip window so `row["content"] == "segment text"` proves transcript alignment rather than a fallback string.

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k transcript_backed_audio`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/tests/test_worker_ingest.py rag-service/app/services/ingestion.py
git commit -m "feat: add transcript text vectors for audio clips"
```

## Chunk 4: Fallback and Observability

### Task 6: Add failing tests for soft-failure paths

**Files:**
- Modify: `rag-service/tests/test_worker_ingest.py`
- Modify: `rag-service/tests/test_audio_metadata.py`
- Modify: `rag-service/app/services/ingestion.py`

- [x] **Step 1: Write the failing test**

```python
async def test_run_ingest_job_keeps_text_only_audio_chunk_when_audio_embed_fails(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}],
        audio_metadata={
            "status": "ok",
            "provider": "whisper",
            "transcript": "segment text",
            "segments": [
                {"start_second": 10, "end_second": 18, "text": "segment text", "confidence": 0.91, "speaker_label": None}
            ],
        },
    )

    async def fake_embed_audio(**_kwargs):
        raise RuntimeError("embed failed")

    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        return {"values": [0.5, 0.6], "model": "text-model", "embed_version": "text-2", "dimension": 2}

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text)

    rows, vector_indices, _diff = await service._build_chunk_rows(document, loaded)

    assert any(row["modality"] == "text" for row in rows)
    assert vector_indices
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k text_only_audio`
Expected: FAIL because audio embed exceptions currently abort the audio path.

- [x] **Step 3: Write minimal implementation**

```python
try:
    audio_embedding = await embed_audio_content(...)
except Exception:
    audio_embedding = None
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k text_only_audio`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/tests/test_worker_ingest.py rag-service/tests/test_audio_metadata.py rag-service/app/services/ingestion.py
git commit -m "feat: preserve audio transcript fallback on soft failures"
```

### Task 7: Record clip and transcript quality metadata

**Files:**
- Modify: `rag-service/app/services/ingestion.py`
- Modify: `rag-service/tests/test_worker_ingest.py`

- [x] **Step 1: Write the failing test**

```python
async def test_run_ingest_job_records_audio_quality_metadata(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}],
        audio_metadata={
            "status": "ok",
            "provider": "whisper",
            "transcript": "a b",
            "segments": [
                {"start_second": 0, "end_second": 8, "text": "a", "confidence": 0.9, "speaker_label": None},
                {"start_second": 10, "end_second": 20, "text": "b", "confidence": 0.8, "speaker_label": None},
            ],
        },
    )

    rows, _vector_indices, _diff = await service._build_chunk_rows(document, loaded)
    assert document.metadata_json["audio_metadata"]["segment_count"] == 2
    assert document.metadata_json["audio_metadata"]["transcript_coverage_seconds"] == 18
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k audio_quality_metadata`
Expected: FAIL because coverage/count metadata is not persisted yet.

- [x] **Step 3: Write minimal implementation**

```python
metadata["audio_metadata"]["segment_count"] = len(metadata["audio_metadata"]["segments"])
metadata["audio_metadata"]["transcript_coverage_seconds"] = _sum_segment_coverage(...)
```

Coverage helper contract:
- Add `_sum_segment_coverage(segments: list[dict[str, object]]) -> int` in `ingestion.py`.
- Compute `max(0, end_second - start_second)` for each normalized segment and return the integer sum.
- Do not attempt interval de-duplication in this iteration; coverage is a simple additive quality signal, not an exact speech occupancy metric.

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_worker_ingest.py -k audio_quality_metadata`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rag-service/app/services/ingestion.py rag-service/tests/test_worker_ingest.py
git commit -m "feat: record audio ingestion quality metadata"
```

## Chunk 5: Verification

### Task 8: Run focused verification suites

**Files:**
- Test: `rag-service/tests/test_audio_metadata.py`
- Test: `rag-service/tests/test_media.py`
- Test: `rag-service/tests/test_loaders.py`
- Test: `rag-service/tests/test_worker_ingest.py`
- Test: `rag-service/tests/test_ingestion_service.py`

- [x] **Step 1: Run focused suite**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_audio_metadata.py tests/test_media.py tests/test_loaders.py tests/test_worker_ingest.py tests/test_ingestion_service.py`
Expected: PASS with new audio retrieval accuracy coverage.

- [x] **Step 2: Fix regressions**

```text
If any failures remain, address them in the same chunk before continuing.
```

- [ ] **Step 3: Commit**

```bash
git add rag-service/app/services/audio_metadata.py rag-service/app/services/ingestion.py rag-service/app/services/loaders.py rag-service/app/services/media.py rag-service/tests/test_audio_metadata.py rag-service/tests/test_ingestion_service.py rag-service/tests/test_loaders.py rag-service/tests/test_media.py rag-service/tests/test_worker_ingest.py
git commit -m "test: verify audio retrieval accuracy pipeline"
```

### Task 9: Run broader regression checks

**Files:**
- Test: `rag-service/tests/test_embedder.py`
- Test: `rag-service/tests/test_query_service.py`
- Test: `rag-service/tests/test_vector_store.py`
- Test: `rag-service/tests/test_api_endpoints.py`

- [x] **Step 1: Run broader regression suite**

Run: `cd /Users/ibrahim/Desktop/rag-pipeline/rag-service && ENV_FILE=.env.test .venv313/bin/python -m pytest -q tests/test_embedder.py tests/test_query_service.py tests/test_vector_store.py tests/test_api_endpoints.py`
Expected: PASS

- [x] **Step 2: Confirm green and record exact pass counts**

```text
Update implementation notes or PR description with the exact command results once verified.
```

## Notes

- This plan extends the completed audio metadata work in `docs/superpowers/plans/2026-03-28-audio-metadata-pipeline.md`.
- Keep audio metadata extraction best-effort; only source loading and unsupported format validation should remain hard failures.
- Do not add diarization or VAD in this plan; reserve those for a follow-up once clip-scoped retrieval quality is verified.
- `rag-service/app/services/loaders.py` already calls `probe_audio_duration_seconds(...)` and `build_clip_ranges(...)`; this plan upgrades those internals rather than adding a separate loader behavior change task.
