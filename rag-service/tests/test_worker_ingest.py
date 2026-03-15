from uuid import UUID

import pytest
from arq.worker import Retry

from app.schemas.ingest import IngestRequest
from app.services import ingestion as ingestion_service_module
from app.services.ingestion import IngestionService
from workers.tasks.ingest import run_ingest_job


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


@pytest.mark.asyncio
async def test_run_ingest_job_processes_async_job(
    integration_session,
    seeded_project,
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
        seeded_project["project_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "project_id": str(seeded_project["project_id"]),
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
    assert vector_store.upsert_calls[0]["chunks"][0]["tenant_id"] == str(seeded_project["tenant_id"])
    assert vector_store.upsert_calls[0]["chunks"][0]["scope_type"] == "project"
    assert vector_store.upsert_calls[0]["chunks"][0]["scope_id"] == str(seeded_project["project_id"])


@pytest.mark.asyncio
async def test_run_ingest_job_creates_parent_child_chunks(
    integration_session,
    seeded_project,
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
        seeded_project["project_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "project_id": str(seeded_project["project_id"]),
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
    seeded_project,
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
        seeded_project["project_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "project_id": str(seeded_project["project_id"]),
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
    seeded_project,
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
        seeded_project["project_id"],
    )

    payload = {
        "document_id": created["document_id"],
        "ingestion_job_id": created["ingestion_job_id"],
        "project_id": str(seeded_project["project_id"]),
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
