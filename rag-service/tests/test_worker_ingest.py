from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from arq.worker import Retry

from app.schemas.ingest import IngestRequest
from app.services import ingestion as ingestion_service_module
from app.services.ingestion import IngestionService
from workers.tasks.ingest import run_ingest_job, run_stale_reembed_scan


class FakeDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, str]] = []

    async def enqueue(self, payload: dict[str, str]) -> None:
        self.enqueued.append(payload)


class FakeVectorStore:
    def __init__(self) -> None:
        self.collections_ensured = 0
        self.upsert_calls: list[dict[str, object]] = []

    async def ensure_collection(self) -> None:
        self.collections_ensured += 1

    async def upsert_chunks(self, chunks: list[dict[str, object]]) -> list[str]:
        self.upsert_calls.append({"chunks": chunks})
        return [f"00000000-0000-0000-0000-{index + 1:012d}" for index, _ in enumerate(chunks)]

    async def find_semantic_duplicate(self, **kwargs):
        return None


def build_loaded_audio_payload(
    *,
    clips: list[dict[str, int]],
    audio_metadata: dict[str, object] | None = None,
    audio_bytes: bytes = b"ID3voice",
) -> dict[str, object]:
    return {
        "content": "voice.mp3",
        "metadata": {
            "title": "voice.mp3",
            "loader_strategy": "gemini_audio_clipped",
            "mime_type": "audio/mpeg",
            "binary_size_bytes": 1234,
            "modality": "audio",
            "url": "https://example.com/voice.mp3",
            "duration_seconds": clips[-1]["end_second"] if clips else 1,
            "clip_count": len(clips),
            "clips": clips,
            **({"audio_metadata": audio_metadata} if audio_metadata is not None else {}),
        },
        "audio_bytes": audio_bytes,
        "chunk_count": len(clips),
    }


def build_audio_document() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        title="voice.mp3",
        source_ref="https://example.com/voice.mp3",
        source_type="audio",
        metadata_json={},
    )


@pytest.mark.asyncio
async def test_run_ingest_job_processes_async_job(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        assert source_type == "web"
        assert source_ref == "https://example.com/article"
        return {
            "content": "Example article body",
            "metadata": {"title": "Example Article", "content_length": 20},
            "chunk_count": 1,
        }

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    async def fake_embed_text(content, title):
        assert content == "Example article body"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "web",
        "source_ref": "https://example.com/article",
    }
    result = await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    document = await service.repository.get_document(UUID(created["document_id"]))
    job = await service.repository.get_job(UUID(created["ingestion_job_id"]))
    chunks = await service.repository.get_document_chunks(UUID(created["document_id"]))

    assert result["status"] == "completed"
    assert document is not None
    assert document.status == "indexed"
    assert document.metadata_json["content_text"] == "Example article body"
    assert document.content_hash != ""
    assert document.embed_model == "gemini-test"
    assert job is not None
    assert job.status == "completed"
    assert job.chunks_processed == 1
    assert len(chunks) == 2
    child_chunk = next(chunk for chunk in chunks if chunk.parent_chunk_id is not None)
    assert child_chunk.qdrant_point_id is not None
    assert child_chunk.embed_model == "gemini-test"
    assert child_chunk.embed_version == "v1"
    assert child_chunk.dimension == 3
    assert len(getattr(child_chunk, "content_hash")) == 64
    assert vector_store.collections_ensured == 1
    assert len(vector_store.upsert_calls) == 1
    assert vector_store.upsert_calls[0]["chunks"][0]["content"] == "Example article body"
    assert vector_store.upsert_calls[0]["chunks"][0]["tenant_id"] == str(seeded_application["tenant_id"])
    assert vector_store.upsert_calls[0]["chunks"][0]["scope_type"] == "project"
    assert vector_store.upsert_calls[0]["chunks"][0]["scope_id"] == str(seeded_application["application_id"])
    assert vector_store.upsert_calls[0]["chunks"][0]["sparse_vector"]["indices"]


@pytest.mark.asyncio
async def test_run_ingest_job_creates_parent_child_chunks(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        return {
            "content": "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
            "metadata": {"title": "Example Article", "content_length": 64},
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "web",
        "source_ref": "https://example.com/article",
    }
    await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    chunks = await service.repository.get_document_chunks(UUID(created["document_id"]))

    assert len(chunks) == 2
    parent = next(chunk for chunk in chunks if chunk.parent_chunk_id is None)
    child = next(chunk for chunk in chunks if chunk.parent_chunk_id is not None)
    assert child.parent_chunk_id == parent.id
    assert parent.qdrant_point_id is None
    assert child.qdrant_point_id is not None


@pytest.mark.asyncio
async def test_run_ingest_job_records_retry_and_raises_retry(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def failing_load(source_type, source_ref):
        raise RuntimeError("loader exploded")

    monkeypatch.setattr(ingestion_service_module, "load_source", failing_load, raising=False)

    service = IngestionService(integration_session, dispatcher=FakeDispatcher())
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "web",
        "source_ref": "https://example.com/article",
    }

    with pytest.raises(Retry):
        await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    job = await service.repository.get_job(UUID(created["ingestion_job_id"]))
    document = await service.repository.get_document(UUID(created["document_id"]))
    assert job is not None
    assert job.status == "pending"
    assert job.retry_count == 1
    assert job.error_message == "loader exploded"
    assert document is not None
    assert document.status == "pending"


@pytest.mark.asyncio
async def test_run_ingest_job_marks_failure_after_final_retry(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def failing_load(source_type, source_ref):
        raise RuntimeError("loader exploded")

    monkeypatch.setattr(ingestion_service_module, "load_source", failing_load, raising=False)

    service = IngestionService(integration_session, dispatcher=FakeDispatcher())
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="pdf",
            source_ref="https://example.com/report.pdf",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "pdf",
        "source_ref": "https://example.com/report.pdf",
    }
    result = await run_ingest_job({"ingestion_service": service, "job_try": 3}, payload)

    job = await service.repository.get_job(UUID(created["ingestion_job_id"]))
    document = await service.repository.get_document(UUID(created["document_id"]))

    assert result["status"] == "failed"
    assert job is not None
    assert job.status == "failed"
    assert job.retry_count == 3
    assert job.error_message == "loader exploded"
    assert document is not None
    assert document.status == "failed"


@pytest.mark.asyncio
async def test_run_stale_reembed_scan_calls_service():
    calls: list[int] = []

    class FakeIngestionService:
        async def requeue_stale_documents(self, *, limit: int = 100):
            calls.append(limit)
            return {"stale_document_count": 2}

    result = await run_stale_reembed_scan({"ingestion_service": FakeIngestionService()})

    assert result == {"stale_document_count": 2}
    assert calls == [100]


@pytest.mark.asyncio
async def test_run_ingest_job_triggers_callback_on_completion(
    integration_session,
    seeded_application,
    monkeypatch,
):
    callbacks: list[dict[str, object]] = []

    async def fake_load(source_type, source_ref):
        return {
            "content": "Example article body",
            "metadata": {"title": "Example Article", "content_length": 20},
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    async def fake_send_ingestion_callback(**payload):
        callbacks.append(payload)

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr("workers.tasks.ingest.send_ingestion_callback", fake_send_ingestion_callback, raising=False)

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            callback_url="https://example.com/callback",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "web",
        "source_ref": "https://example.com/article",
        "callback_url": "https://example.com/callback",
    }
    result = await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    assert result["status"] == "completed"
    assert callbacks[0]["callback_url"] == "https://example.com/callback"
    assert callbacks[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_ingest_job_triggers_callback_on_final_failure_without_breaking_result(
    integration_session,
    seeded_application,
    monkeypatch,
):
    callbacks: list[dict[str, object]] = []

    async def failing_load(source_type, source_ref):
        raise RuntimeError("loader exploded")

    async def fake_send_ingestion_callback(**payload):
        callbacks.append(payload)
        raise RuntimeError("callback failed")

    monkeypatch.setattr(ingestion_service_module, "load_source", failing_load, raising=False)
    monkeypatch.setattr("workers.tasks.ingest.send_ingestion_callback", fake_send_ingestion_callback, raising=False)

    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=FakeVectorStore(),
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            callback_url="https://example.com/callback",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "web",
        "source_ref": "https://example.com/article",
        "callback_url": "https://example.com/callback",
    }
    result = await run_ingest_job({"ingestion_service": service, "job_try": 3}, payload)

    assert result["status"] == "failed"
    assert callbacks[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_run_ingest_job_records_audio_clip_rows(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        assert source_type == "audio"
        assert source_ref == "https://example.com/voice.mp3"
        return {
            "content": "voice.mp3",
            "metadata": {
                "title": "voice.mp3",
                "loader_strategy": "gemini_audio_clipped",
                "mime_type": "audio/mpeg",
                "binary_size_bytes": 1234,
                "modality": "audio",
                "url": "https://example.com/voice.mp3",
                "duration_seconds": 255,
                "clip_count": 3,
                "clips": [
                    {"clip_index": 0, "start_second": 0, "end_second": 120},
                    {"clip_index": 1, "start_second": 120, "end_second": 240},
                    {"clip_index": 2, "start_second": 240, "end_second": 255},
                ],
            },
            "audio_bytes": b"ID3voice",
            "chunk_count": 3,
        }

    async def fake_embed_audio(audio_bytes, title, mime_type):
        assert audio_bytes == b"ID3voice"
        assert mime_type == "audio/mpeg"
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_audio_content",
        fake_embed_audio,
        raising=False,
    )

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="audio",
            source_ref="https://example.com/voice.mp3",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "audio",
        "source_ref": "https://example.com/voice.mp3",
    }
    result = await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    document = await service.repository.get_document(UUID(created["document_id"]))
    chunks = await service.repository.get_document_chunks(UUID(created["document_id"]))

    assert result["status"] == "completed"
    assert document is not None
    assert document.status == "indexed"
    assert document.chunk_count == 3
    assert document.metadata_json["loader"]["clip_count"] == 3
    assert document.metadata_json["audio_metadata"]["segment_count"] == 0
    assert document.metadata_json["audio_metadata"]["transcript_coverage_seconds"] == 0
    assert len(chunks) == 6
    assert sum(1 for chunk in chunks if chunk.parent_chunk_id is not None) == 3
    assert all(chunk.modality == "audio" for chunk in chunks)


@pytest.mark.asyncio
async def test_run_ingest_job_enriches_audio_chunks_with_transcript_metadata(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        return {
            "content": "voice.mp3",
            "metadata": {
                "title": "voice.mp3",
                "loader_strategy": "gemini_audio_clipped",
                "mime_type": "audio/mpeg",
                "binary_size_bytes": 1234,
                "modality": "audio",
                "url": "https://example.com/voice.mp3",
                "duration_seconds": 140,
                "clip_count": 2,
                "clips": [
                    {"clip_index": 0, "start_second": 0, "end_second": 120},
                    {"clip_index": 1, "start_second": 120, "end_second": 140},
                ],
            },
            "audio_bytes": b"ID3voice",
            "chunk_count": 2,
        }

    async def fake_embed_audio(audio_bytes, title, mime_type):
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        assert content in {
            "speaker one mentions invoice INV-1001",
            "speaker two closes the call",
        }
        return {
            "provider": "gemini",
            "model": "gemini-text",
            "task_type": task_type,
            "embed_version": "gemini-text-3",
            "status": "completed",
            "values": [0.4, 0.5, 0.6],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "ok",
            "provider": "whisper",
            "transcript": "speaker one mentions invoice INV-1001. speaker two closes the call.",
            "segments": [
                {
                    "segment_index": 0,
                    "start_second": 5,
                    "end_second": 35,
                    "text": "speaker one mentions invoice INV-1001",
                    "speaker_label": "SPEAKER_00",
                },
                {
                    "segment_index": 1,
                    "start_second": 122,
                    "end_second": 135,
                    "text": "speaker two closes the call",
                    "speaker_label": "SPEAKER_01",
                },
            ],
        }

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "extract_audio_metadata",
        fake_extract_audio_metadata,
        raising=False,
    )

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="audio",
            source_ref="https://example.com/voice.mp3",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "audio",
        "source_ref": "https://example.com/voice.mp3",
    }
    await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    document = await service.repository.get_document(UUID(created["document_id"]))
    chunks = await service.repository.get_document_chunks(UUID(created["document_id"]))
    parent_chunks = [chunk for chunk in chunks if chunk.parent_chunk_id is None]
    text_chunks = [chunk for chunk in chunks if chunk.parent_chunk_id is not None and chunk.modality == "text"]

    assert document is not None
    assert document.metadata_json["audio_metadata"]["status"] == "ok"
    assert document.metadata_json["audio_metadata"]["provider"] == "whisper"
    assert len(document.metadata_json["audio_metadata"]["segments"]) == 2
    assert document.metadata_json["audio_metadata"]["segment_count"] == 2
    assert document.metadata_json["audio_metadata"]["transcript_coverage_seconds"] == 43
    assert "invoice INV-1001" in parent_chunks[0].content
    assert "closes the call" in parent_chunks[1].content
    assert len(text_chunks) == 2


@pytest.mark.asyncio
async def test_run_ingest_job_keeps_audio_summary_when_metadata_unavailable(
    integration_session,
    seeded_application,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        return {
            "content": "voice.mp3",
            "metadata": {
                "title": "voice.mp3",
                "loader_strategy": "gemini_audio_clipped",
                "mime_type": "audio/mpeg",
                "binary_size_bytes": 1234,
                "modality": "audio",
                "url": "https://example.com/voice.mp3",
                "duration_seconds": 95,
                "clip_count": 1,
                "clips": [
                    {"clip_index": 0, "start_second": 0, "end_second": 95},
                ],
            },
            "audio_bytes": b"ID3voice",
            "chunk_count": 1,
        }

    async def fake_embed_audio(audio_bytes, title, mime_type):
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "unavailable",
            "provider": "whisper",
            "transcript": None,
            "segments": [],
        }

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "extract_audio_metadata",
        fake_extract_audio_metadata,
        raising=False,
    )

    vector_store = FakeVectorStore()
    service = IngestionService(
        integration_session,
        dispatcher=FakeDispatcher(),
        vector_store=vector_store,
    )
    created = await service.create_ingestion_job(
        IngestRequest(
            source_type="audio",
            source_ref="https://example.com/voice.mp3",
            mode="async",
        ),
        seeded_application["application_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "application_id": str(seeded_application["application_id"]),
        "source_type": "audio",
        "source_ref": "https://example.com/voice.mp3",
    }
    await run_ingest_job({"ingestion_service": service, "job_try": 1}, payload)

    document = await service.repository.get_document(UUID(created["document_id"]))
    chunks = await service.repository.get_document_chunks(UUID(created["document_id"]))
    parent_chunks = [chunk for chunk in chunks if chunk.parent_chunk_id is None]

    assert document is not None
    assert document.metadata_json["audio_metadata"]["status"] == "unavailable"
    assert document.metadata_json["audio_metadata"]["segment_count"] == 0
    assert document.metadata_json["audio_metadata"]["transcript_coverage_seconds"] == 0
    assert parent_chunks[0].content == "voice.mp3 clip 1 (0-95s)"


@pytest.mark.asyncio
async def test_run_ingest_job_embeds_each_audio_clip_with_clip_scoped_bytes(
    monkeypatch,
):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[
            {"clip_index": 0, "start_second": 0, "end_second": 120},
            {"clip_index": 1, "start_second": 120, "end_second": 240},
        ]
    )

    embedded_payloads: list[bytes] = []

    async def fake_embed_audio(audio_bytes, title, mime_type):
        embedded_payloads.append(audio_bytes)
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "unavailable",
            "provider": "whisper",
            "transcript": None,
            "segments": [],
        }

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    monkeypatch.setattr(ingestion_service_module, "extract_audio_metadata", fake_extract_audio_metadata, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "slice_audio_clip_bytes",
        lambda _binary, _filename, clips: [
            {**clips[0], "audio_bytes": b"clip-a"},
            {**clips[1], "audio_bytes": b"clip-b"},
        ],
        raising=False,
    )

    service = IngestionService(object(), dispatcher=FakeDispatcher(), vector_store=FakeVectorStore())

    await service._build_chunk_rows(document, loaded)

    assert embedded_payloads == [b"clip-a", b"clip-b"]


@pytest.mark.asyncio
async def test_run_ingest_job_creates_text_vector_for_transcript_backed_audio_clip(
    monkeypatch,
):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}]
    )

    async def fake_embed_audio(audio_bytes, title, mime_type):
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        assert content == "segment text"
        return {
            "provider": "gemini",
            "model": "gemini-text",
            "task_type": task_type,
            "embed_version": "gemini-text-3",
            "status": "completed",
            "values": [0.3, 0.4, 0.5],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "ok",
            "provider": "whisper",
            "transcript": "segment text",
            "segments": [
                {
                    "segment_index": 0,
                    "start_second": 10,
                    "end_second": 18,
                    "text": "segment text",
                    "speaker_label": None,
                }
            ],
        }

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr(ingestion_service_module, "extract_audio_metadata", fake_extract_audio_metadata, raising=False)

    service = IngestionService(object(), dispatcher=FakeDispatcher(), vector_store=FakeVectorStore())

    rows, _vector_indices, _diff = await service._build_chunk_rows(document, loaded)

    assert any(row["modality"] == "text" and row["content"] == "segment text" for row in rows)


@pytest.mark.asyncio
async def test_run_ingest_job_keeps_text_only_audio_chunk_when_audio_embed_fails(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}]
    )

    async def fake_embed_audio(audio_bytes, title, mime_type):
        raise RuntimeError("embed failed")

    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        assert content == "segment text"
        return {
            "provider": "gemini",
            "model": "gemini-text",
            "task_type": task_type,
            "embed_version": "gemini-text-3",
            "status": "completed",
            "values": [0.3, 0.4, 0.5],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "ok",
            "provider": "whisper",
            "transcript": "segment text",
            "segments": [
                {
                    "segment_index": 0,
                    "start_second": 10,
                    "end_second": 18,
                    "text": "segment text",
                    "speaker_label": None,
                }
            ],
        }

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr(ingestion_service_module, "extract_audio_metadata", fake_extract_audio_metadata, raising=False)

    service = IngestionService(object(), dispatcher=FakeDispatcher(), vector_store=FakeVectorStore())

    rows, vector_indices, _diff = await service._build_chunk_rows(document, loaded)

    assert any(row["modality"] == "text" and row["content"] == "segment text" for row in rows)
    assert vector_indices


@pytest.mark.asyncio
async def test_run_ingest_job_records_audio_quality_metadata(monkeypatch):
    document = build_audio_document()
    loaded = build_loaded_audio_payload(
        clips=[{"clip_index": 0, "start_second": 0, "end_second": 120}]
    )

    async def fake_embed_audio(audio_bytes, title, mime_type):
        return {
            "provider": "gemini",
            "model": "gemini-test",
            "task_type": "RETRIEVAL_DOCUMENT",
            "embed_version": "gemini-test-3",
            "status": "completed",
            "values": [0.1, 0.2, 0.3],
            "dimension": 3,
            "vector_dimension": 3,
        }

    async def fake_extract_audio_metadata(audio_bytes, *, filename=None):
        return {
            "status": "ok",
            "provider": "whisper",
            "transcript": "a b",
            "segments": [
                {
                    "segment_index": 0,
                    "start_second": 0,
                    "end_second": 8,
                    "text": "a",
                    "speaker_label": None,
                },
                {
                    "segment_index": 1,
                    "start_second": 10,
                    "end_second": 20,
                    "text": "b",
                    "speaker_label": None,
                },
            ],
        }

    monkeypatch.setattr(ingestion_service_module, "embed_audio_content", fake_embed_audio, raising=False)
    async def fake_embed_text(content, title, *, task_type="RETRIEVAL_DOCUMENT"):
        return {
            "provider": "gemini",
            "model": "gemini-text",
            "task_type": task_type,
            "embed_version": "gemini-text-3",
            "status": "completed",
            "values": [0.3, 0.4, 0.5],
            "dimension": 3,
            "vector_dimension": 3,
        }

    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )
    monkeypatch.setattr(ingestion_service_module, "extract_audio_metadata", fake_extract_audio_metadata, raising=False)

    service = IngestionService(object(), dispatcher=FakeDispatcher(), vector_store=FakeVectorStore())

    await service._build_chunk_rows(document, loaded)

    assert loaded["metadata"]["audio_metadata"]["segment_count"] == 2
    assert loaded["metadata"]["audio_metadata"]["transcript_coverage_seconds"] == 18
