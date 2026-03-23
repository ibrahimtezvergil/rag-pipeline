import pytest
from uuid import UUID
from fastapi import HTTPException
from types import SimpleNamespace

from app.models.db import RagChunk
from app.config import get_settings
from app.schemas.ingest import IngestRequest
from app.services import ingestion as ingestion_service_module
from app.services import loaders as loaders_module
from app.services.ingestion import IngestionService


class FakeDispatcher:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, str]] = []

    async def enqueue(self, payload: dict[str, str]) -> None:
        self.enqueued.append(payload)


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_point_ids: list[str] = []
        self.collection_ready = False

    async def ensure_collection(self) -> None:
        self.collection_ready = True

    async def fetch_dense_vectors(self, point_ids: list[str]) -> dict[str, list[float]]:
        return {}

    async def upsert_chunks(self, chunks: list[dict[str, object]]) -> list[str]:
        return [f"00000000-0000-0000-0000-{index + 1:012d}" for index, _ in enumerate(chunks)]

    async def find_semantic_duplicate(self, **kwargs):
        assert self.collection_ready is True
        return None

    async def delete_points(self, point_ids: list[str]) -> None:
        self.deleted_point_ids.extend(point_ids)


@pytest.mark.asyncio
async def test_create_ingestion_job_persists_document_and_job(
    integration_session,
    seeded_project,
):
    dispatcher = FakeDispatcher()
    service = IngestionService(integration_session, dispatcher=dispatcher)

    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="pdf",
            source_ref="https://example.com/files/report.pdf",
            mode="async",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "pending"
    assert result["mode"] == "async"
    assert result["source_type"] == "pdf"
    assert dispatcher.enqueued == [
        {
            "document_id": result["document_id"],
            "ingestion_job_id": result["ingestion_job_id"],
            "project_id": str(seeded_project["project_id"]),
            "source_type": "pdf",
            "source_ref": "https://example.com/files/report.pdf",
        }
    ]

    job_status = await service.get_ingestion_job(result["ingestion_job_id"])
    assert job_status == {
        "document_id": result["document_id"],
        "ingestion_job_id": result["ingestion_job_id"],
        "status": "pending",
        "job_type": "ingest",
        "source_type": "pdf",
    }


@pytest.mark.asyncio
async def test_create_ingestion_batch_persists_multiple_jobs(
    integration_session,
    seeded_project,
):
    dispatcher = FakeDispatcher()
    service = IngestionService(integration_session, dispatcher=dispatcher)

    results = await service.create_ingestion_batch(
        [
            IngestRequest(
                source_type="pdf",
                source_ref="https://example.com/files/report-1.pdf",
                mode="async",
            ),
            IngestRequest(
                source_type="web",
                source_ref="https://example.com/article-1",
                mode="async",
            ),
        ],
        seeded_project["project_id"],
    )

    assert len(results) == 2
    assert results[0]["status"] == "pending"
    assert results[1]["status"] == "pending"
    assert dispatcher.enqueued == [
        {
            "document_id": results[0]["document_id"],
            "ingestion_job_id": results[0]["ingestion_job_id"],
            "project_id": str(seeded_project["project_id"]),
            "source_type": "pdf",
            "source_ref": "https://example.com/files/report-1.pdf",
        },
        {
            "document_id": results[1]["document_id"],
            "ingestion_job_id": results[1]["ingestion_job_id"],
            "project_id": str(seeded_project["project_id"]),
            "source_type": "web",
            "source_ref": "https://example.com/article-1",
        },
    ]


@pytest.mark.asyncio
async def test_create_ingestion_batch_rejects_sync_items(
    integration_session,
    seeded_project,
):
    service = IngestionService(integration_session, dispatcher=FakeDispatcher())

    with pytest.raises(HTTPException) as exc:
        await service.create_ingestion_batch(
            [
                IngestRequest(
                    source_type="pdf",
                    source_ref="https://example.com/files/report-1.pdf",
                    mode="sync",
                ),
            ],
            seeded_project["project_id"],
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Batch ingestion only supports async mode"


@pytest.mark.asyncio
async def test_sync_web_ingestion_stores_loaded_metadata(
    integration_session,
    seeded_project,
    monkeypatch,
):
    events: list[tuple[str, dict[str, object]]] = []

    async def fake_load(source_type, source_ref):
        assert source_type == "web"
        assert source_ref == "https://example.com/article"
        return {
            "content": "Example article body",
            "metadata": {
                "title": "Example Article",
                "content_length": 20,
                "loader_strategy": "crawl4ai_rendered",
            },
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        assert content == "Example article body"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )
    monkeypatch.setattr(
        ingestion_service_module,
        "emit_event",
        lambda event, payload: events.append((event, payload)),
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "completed"

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "Example Article"
    assert document.chunk_count == 1
    assert document.metadata_json["loader"] == {
        "title": "Example Article",
        "content_length": 20,
        "loader_strategy": "crawl4ai_rendered",
    }
    assert len(events) == 1
    event_name, payload = events[0]
    assert event_name == "ingestion.chunk_indexed"
    assert payload["tenant_id"] == str(seeded_project["tenant_id"])
    assert payload["project_id"] == str(seeded_project["project_id"])
    assert payload["document_id"] == result["document_id"]
    assert payload["chunk_index"] == 0
    assert payload["modality"] == "text"
    assert payload["vector_dimension"] == 3
    assert payload["token_count"] == len("Example article body") // 4
    assert isinstance(payload["embed_ms"], int)


@pytest.mark.asyncio
async def test_sync_ingest_marks_document_and_job_failed_when_processing_raises(monkeypatch):
    project_id = UUID("22222222-2222-2222-2222-222222222222")
    tenant_id = UUID("11111111-1111-1111-1111-111111111111")
    document = SimpleNamespace(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        project_id=project_id,
        tenant_id=tenant_id,
        status="indexing",
        source_type="web",
        source_ref="https://example.com/article",
        previous_document_id=None,
        metadata_json={},
    )
    job = SimpleNamespace(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        document_id=document.id,
        status="running",
        error_message=None,
    )
    updated: dict[str, object] = {}

    class FakeRepository:
        async def get_project(self, raw_project_id):
            return SimpleNamespace(id=project_id, tenant_id=tenant_id, config={})

        async def get_latest_document_by_source_ref(self, raw_project_id, source_ref):
            return None

        async def create_document(self, **kwargs):
            return document

        async def create_job(self, **kwargs):
            return job

        async def update_document_status(self, target_document, status):
            updated["document_status"] = status
            target_document.status = status

        async def update_job_status(self, target_job, status, **kwargs):
            updated["job_status"] = status
            updated["error_message"] = kwargs.get("error_message")
            target_job.status = status
            target_job.error_message = kwargs.get("error_message")

        async def commit(self):
            updated["committed"] = True

    service = IngestionService(session=None, vector_store=FakeVectorStore())
    service.repository = FakeRepository()

    async def fake_process(target_document, target_job, retry_count=0):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_process_document_job", fake_process)

    with pytest.raises(RuntimeError):
        await service.create_ingestion_job(
            IngestRequest(
                source_type="web",
                source_ref="https://example.com/article",
                mode="sync",
            ),
            project_id,
        )

    assert updated == {
        "document_status": "failed",
        "job_status": "failed",
        "error_message": "boom",
        "committed": True,
    }
    assert document.status == "failed"
    assert job.status == "failed"
    assert job.error_message == "boom"


@pytest.mark.asyncio
async def test_sync_web_ingestion_uses_real_web_loader_metadata(
    integration_session,
    seeded_project,
    monkeypatch,
):
    html = """
    <html>
      <head><title>Rendered Article</title></head>
      <body>
        <nav>Navigation</nav>
        <main><p>Rendered body.</p></main>
        <footer>Footer links</footer>
      </body>
    </html>
    """

    async def fake_render(source_ref):
        assert source_ref == "https://example.com/article"
        return {
            "html": html,
            "final_url": "https://example.com/rendered",
        }

    class FakeResponse:
        text = html
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, source_ref):
            raise AssertionError(f"static fallback should not run for {source_ref}")

    async def fake_embed_text(content, title):
        assert content == "Rendered Article Rendered body."
        assert title == "Rendered Article"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(loaders_module, "_render_web_with_crawl4ai", fake_render, raising=False)
    monkeypatch.setattr(loaders_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(ingestion_service_module, "load_source", loaders_module.load_source, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "Rendered Article"
    assert document.metadata_json["loader"] == {
        "title": "Rendered Article",
        "content_length": len("Rendered Article Rendered body."),
        "url": "https://example.com/rendered",
        "loader_strategy": "crawl4ai_rendered",
    }


@pytest.mark.asyncio
async def test_sync_pdf_ingestion_stores_loaded_metadata(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_resolve_pdf_embedding(source_ref, content, metadata):
        assert source_ref == "https://example.com/files/report.pdf"
        assert content == "Parsed PDF text"
        assert metadata["loader_strategy"] == "gemini_direct_pdf"
        return {
            "provider": "gemini",
            "status": "completed",
            "task_type": "RETRIEVAL_DOCUMENT",
            "vector_dimension": 768,
        }

    async def fake_load(source_type, source_ref):
        assert source_type == "pdf"
        assert source_ref == "https://example.com/files/report.pdf"
        return {
                "content": "Parsed PDF text",
                "metadata": {
                    "title": "report.pdf",
                    "page_count": 3,
                    "loader_strategy": "gemini_direct_pdf",
                    "direct_embed_ready": True,
                    "binary_size_bytes": 2048,
                    "modality": "pdf",
            },
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        assert content == "Parsed PDF text"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "resolve_pdf_embedding",
        fake_resolve_pdf_embedding,
        raising=False,
    )
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="pdf",
            source_ref="https://example.com/files/report.pdf",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "completed"

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "report.pdf"
    assert document.chunk_count == 1
    assert document.metadata_json["loader"] == {
        "title": "report.pdf",
        "page_count": 3,
        "loader_strategy": "gemini_direct_pdf",
        "direct_embed_ready": True,
        "binary_size_bytes": 2048,
        "modality": "pdf",
    }
    assert document.metadata_json["embedding"] == {
        "provider": "gemini",
        "status": "completed",
        "task_type": "RETRIEVAL_DOCUMENT",
        "vector_dimension": 768,
    }


@pytest.mark.asyncio
async def test_sync_pdf_ingestion_preserves_loader_path_metadata(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_load(source_type, source_ref):
        return {
            "content": (
                "Parsed PDF text with enough words for chunk one\n"
                "Parsed PDF text with enough words for chunk two"
            ),
            "metadata": {
                "title": "report.pdf",
                "page_count": 8,
                "loader_strategy": "pymupdf_layout_chunked",
                "pages": [{"page_number": 1}, {"page_number": 2}],
                "chunks": [
                    {"chunk_index": 0, "page_start": 1, "page_end": 1},
                    {"chunk_index": 1, "page_start": 2, "page_end": 2},
                ],
            },
            "chunk_count": 2,
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

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="pdf",
            source_ref="https://example.com/files/report.pdf",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.chunk_count == 2
    assert document.metadata_json["loader"]["loader_strategy"] == "pymupdf_layout_chunked"
    assert document.metadata_json["loader"]["pages"] == [{"page_number": 1}, {"page_number": 2}]


@pytest.mark.asyncio
async def test_sync_image_ingestion_stores_direct_embed_metadata_and_vector_row(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_load(source_type, source_ref=None, **kwargs):
        assert source_type == "image"
        assert source_ref == "https://example.com/avatar.png"
        return {
            "content": "avatar.png",
            "metadata": {
                "title": "avatar.png",
                "loader_strategy": "gemini_direct_image",
                "mime_type": "image/png",
                "binary_size_bytes": 15,
                "modality": "image",
                "url": "https://example.com/avatar.png",
            },
            "image_bytes": b"\x89PNG\r\n\x1a\nfakepng",
            "chunk_count": 1,
        }

    async def fake_embed_image(image_bytes, title, mime_type):
        assert image_bytes == b"\x89PNG\r\n\x1a\nfakepng"
        assert title == "avatar.png"
        assert mime_type == "image/png"
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
        "embed_image_content",
        fake_embed_image,
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="image",
            source_ref="https://example.com/avatar.png",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "completed"

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "avatar.png"
    assert document.chunk_count == 1
    assert document.metadata_json["loader"] == {
        "title": "avatar.png",
        "loader_strategy": "gemini_direct_image",
        "mime_type": "image/png",
        "binary_size_bytes": 15,
        "modality": "image",
        "url": "https://example.com/avatar.png",
    }
    assert document.metadata_json["embedding"] == {
        "provider": "gemini",
        "model": "gemini-test",
        "task_type": "RETRIEVAL_DOCUMENT",
        "embed_version": "gemini-test-3",
        "status": "completed",
        "values": [0.1, 0.2, 0.3],
        "dimension": 3,
        "vector_dimension": 3,
    }

    chunks = await service.repository.get_document_chunks(document.id)
    assert len(chunks) == 2
    assert chunks[0].modality == "image"
    assert chunks[1].modality == "image"
    assert chunks[1].embed_model == "gemini-test"


@pytest.mark.asyncio
async def test_sync_db_ingestion_formats_sql_result_and_indexes_document(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_load(source_type, source_ref=None, **kwargs):
        assert source_type == "db"
        assert source_ref is None
        assert kwargs["source_sql"] == "SELECT customer, plan FROM accounts"
        return {
            "content": "SQL Query Result\n\nRow 1: customer is Acme. plan is growth.",
            "metadata": {
                "title": "SQL Query Result",
                "row_count": 1,
                "query": "SELECT customer, plan FROM accounts",
            },
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        assert "customer is Acme" in content
        assert title == "SQL Query Result"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="db",
            source_sql="SELECT customer, plan FROM accounts",
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "completed"

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "SQL Query Result"
    assert document.chunk_count == 1
    assert document.source_ref == "inline://sql-query"
    assert document.metadata_json["loader"] == {
        "title": "SQL Query Result",
        "row_count": 1,
        "query": "SELECT customer, plan FROM accounts",
    }


@pytest.mark.asyncio
async def test_sync_structured_ingestion_persists_scope_metadata_and_indexes_document(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_load(source_type, source_ref=None, **kwargs):
        assert source_type == "structured"
        assert source_ref is None
        assert kwargs["title"] == "CRM Customer Snapshot"
        assert kwargs["records"] == [
            {
                "customer_id": 42,
                "company_name": "Acme Mobilya",
                "stage": "negotiation",
            }
        ]
        assert kwargs["scope_type"] == "customer"
        assert kwargs["scope_id"] == "cust_42"
        assert kwargs["entity_type"] == "customer"
        assert kwargs["origin"] == "crm"
        assert kwargs["entity_id"] == "cust_42"
        assert kwargs["record_ids"] == ["opp_91", "note_18"]
        assert kwargs["snapshot_date"] == "2026-03-15"
        assert kwargs["tags"] == ["crm", "daily-sync"]
        return {
            "content": (
                "CRM Customer Snapshot\n\n"
                "Row 1: customer_id is 42. company_name is Acme Mobilya. stage is negotiation."
            ),
            "metadata": {
                "title": "CRM Customer Snapshot",
                "record_count": 1,
                "formatter_model": "gemini-test",
                "formatter_mode": "llm_semantic",
                "scope_type": "customer",
                "scope_id": "cust_42",
                "entity_type": "customer",
                "origin": "crm",
                "entity_id": "cust_42",
                "record_ids": ["opp_91", "note_18"],
                "snapshot_date": "2026-03-15",
                "tags": ["crm", "daily-sync"],
            },
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        assert "company_name is Acme Mobilya" in content
        assert title == "CRM Customer Snapshot"
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "embed_text_content",
        fake_embed_text,
        raising=False,
    )

    service = IngestionService(integration_session, vector_store=FakeVectorStore())
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="structured",
            title="CRM Customer Snapshot",
            records=[
                {
                    "customer_id": 42,
                    "company_name": "Acme Mobilya",
                    "stage": "negotiation",
                }
            ],
            origin="crm",
            entity_id="cust_42",
            record_ids=["opp_91", "note_18"],
            snapshot_date="2026-03-15",
            scope_type="customer",
            scope_id="cust_42",
            entity_type="customer",
            tags=["crm", "daily-sync"],
            mode="sync",
        ),
        seeded_project["project_id"],
    )

    assert result["status"] == "completed"

    document = await service.repository.get_document(UUID(result["document_id"]))
    assert document is not None
    assert document.status == "indexed"
    assert document.title == "CRM Customer Snapshot"
    assert document.chunk_count == 1
    assert document.source_ref == "inline://structured-records"
    assert document.metadata_json["scope_type"] == "customer"
    assert document.metadata_json["scope_id"] == "cust_42"
    assert document.metadata_json["entity_type"] == "customer"
    assert document.metadata_json["origin"] == "crm"
    assert document.metadata_json["entity_id"] == "cust_42"
    assert document.metadata_json["record_ids"] == ["opp_91", "note_18"]
    assert document.metadata_json["snapshot_date"] == "2026-03-15"
    assert document.metadata_json["tags"] == ["crm", "daily-sync"]
    assert document.metadata_json["loader"] == {
        "title": "CRM Customer Snapshot",
        "record_count": 1,
        "formatter_model": "gemini-test",
        "formatter_mode": "llm_semantic",
        "scope_type": "customer",
        "scope_id": "cust_42",
        "entity_type": "customer",
        "origin": "crm",
        "entity_id": "cust_42",
        "record_ids": ["opp_91", "note_18"],
        "snapshot_date": "2026-03-15",
        "tags": ["crm", "daily-sync"],
    }


@pytest.mark.asyncio
async def test_get_ingestion_job_maps_running_to_indexing(
    integration_session,
    seeded_project,
):
    service = IngestionService(integration_session)
    document = await service.repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="pdf",
        source_ref="https://example.com/files/report.pdf",
        status="indexing",
        title="report.pdf",
        content_hash="hash",
        metadata={},
    )
    job = await service.repository.create_job(document_id=document.id, status="running")
    await service.repository.commit()

    result = await service.get_ingestion_job(str(job.id))

    assert result["status"] == "indexing"


@pytest.mark.asyncio
async def test_get_ingestion_job_maps_completed_to_indexed(
    integration_session,
    seeded_project,
):
    service = IngestionService(integration_session)
    document = await service.repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/article",
        status="indexed",
        title="article",
        content_hash="hash",
        metadata={},
    )
    job = await service.repository.create_job(document_id=document.id, status="completed")
    await service.repository.commit()

    result = await service.get_ingestion_job(str(job.id))

    assert result["status"] == "indexed"


@pytest.mark.asyncio
async def test_delete_ingestion_job_soft_deletes_document_and_archives_chunks(
    integration_session,
    seeded_project,
):
    vector_store = FakeVectorStore()
    service = IngestionService(integration_session, vector_store=vector_store)
    document = await service.repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="pdf",
        source_ref="https://example.com/files/report.pdf",
        status="indexed",
        title="report.pdf",
        content_hash="hash",
        metadata={},
    )
    chunk = RagChunk(
        document_id=document.id,
        chunk_index=0,
        modality="text",
        qdrant_point_id=UUID("00000000-0000-0000-0000-000000000123"),
    )
    integration_session.add(chunk)
    job = await service.repository.create_job(document_id=document.id, status="completed")
    await service.repository.commit()

    result = await service.delete_ingestion_job(str(job.id))

    deleted_document = await service.repository.get_document(document.id)
    assert deleted_document is not None
    assert deleted_document.status == "deleted"

    archived_chunk = await integration_session.get(RagChunk, chunk.id)
    assert archived_chunk is not None
    assert archived_chunk.is_archived is True
    assert result == {
        "document_id": str(document.id),
        "ingestion_job_id": str(job.id),
        "archived_chunk_count": 1,
        "qdrant_point_ids": ["00000000-0000-0000-0000-000000000123"],
    }
    assert vector_store.deleted_point_ids == ["00000000-0000-0000-0000-000000000123"]


@pytest.mark.asyncio
async def test_create_chunks_persists_chunk_content(integration_session, seeded_project):
    service = IngestionService(integration_session)
    document = await service.repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Chunk Content Document",
        content_hash="hash",
        metadata={"content_text": "document text"},
    )
    chunks = await service.repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "chunk-hash",
                "content": "Chunk level content for retrieval snippets.",
                "modality": "text",
                "token_count": 6,
                "page_number": None,
                "bbox": None,
                "section_title": "Chunk Section",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            }
        ]
    )
    await service.repository.commit()

    persisted_chunk = await integration_session.get(RagChunk, chunks[0].id)
    assert persisted_chunk is not None
    assert persisted_chunk.content == "Chunk level content for retrieval snippets."


@pytest.mark.asyncio
async def test_create_ingestion_job_updates_trace_metadata(
    monkeypatch,
):
    updates: list[dict[str, object]] = []
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    document_id = UUID("00000000-0000-0000-0000-000000000333")
    job_id = UUID("00000000-0000-0000-0000-000000000444")

    monkeypatch.setattr(
        ingestion_service_module,
        "update_current_observation",
        lambda **kwargs: updates.append(kwargs),
        raising=False,
    )

    service = IngestionService(None, dispatcher=FakeDispatcher())  # type: ignore[arg-type]
    service.repository = SimpleNamespace(
        get_project=lambda value: None,
        create_document=lambda **kwargs: None,
        create_job=lambda **kwargs: None,
        commit=lambda: None,
    )

    async def fake_get_project(value):
        return SimpleNamespace(id=project_id, tenant_id=tenant_id)

    async def fake_create_document(**kwargs):
        return SimpleNamespace(id=document_id)

    async def fake_create_job(**kwargs):
        return SimpleNamespace(id=job_id, status="pending")

    async def fake_commit():
        return None

    async def fake_get_latest_document_by_source_ref(project_id_value, source_ref):
        return None

    service.repository = SimpleNamespace(
        get_project=fake_get_project,
        get_latest_document_by_source_ref=fake_get_latest_document_by_source_ref,
        create_document=fake_create_document,
        create_job=fake_create_job,
        commit=fake_commit,
    )
    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="async",
        ),
        project_id,
    )

    assert updates
    metadata = updates[-1]["metadata"]
    assert metadata["project_id"] == str(project_id)
    assert metadata["document_id"] == result["document_id"]
    assert metadata["source_type"] == "web"
    assert "source_ref" not in metadata


@pytest.mark.asyncio
async def test_create_ingestion_job_invalidates_query_cache_after_sync_success(
    monkeypatch,
):
    invalidated: list[str] = []
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    document_id = UUID("00000000-0000-0000-0000-000000000333")
    job_id = UUID("00000000-0000-0000-0000-000000000444")

    class FakeCache:
        async def invalidate_project(self, project_id: str):
            invalidated.append(project_id)

    service = IngestionService(
        None,  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),
        query_cache=FakeCache(),
    )
    service.repository = SimpleNamespace(
        get_project=lambda value: None,
        create_document=lambda **kwargs: None,
        create_job=lambda **kwargs: None,
        commit=lambda: None,
    )

    async def fake_get_project(value):
        return SimpleNamespace(id=project_id, tenant_id=tenant_id)

    async def fake_create_document(**kwargs):
        return SimpleNamespace(id=document_id, project_id=project_id, tenant_id=tenant_id, metadata_json={})

    async def fake_create_job(**kwargs):
        return SimpleNamespace(id=job_id, status="completed")

    async def fake_commit():
        return None

    async def fake_process_document_job(document, job, *, retry_count):
        await service.query_cache.invalidate_project(str(document.project_id))

    async def fake_get_latest_document_by_source_ref(project_id_value, source_ref):
        return None

    service.repository = SimpleNamespace(
        get_project=fake_get_project,
        get_latest_document_by_source_ref=fake_get_latest_document_by_source_ref,
        create_document=fake_create_document,
        create_job=fake_create_job,
        commit=fake_commit,
    )
    monkeypatch.setattr(service, "_process_document_job", fake_process_document_job, raising=False)

    await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="sync",
        ),
        project_id,
    )

    assert invalidated == [str(project_id)]


@pytest.mark.asyncio
async def test_delete_ingestion_job_invalidates_query_cache(
):
    invalidated: list[str] = []
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    document_id = UUID("00000000-0000-0000-0000-000000000333")
    job_id = UUID("00000000-0000-0000-0000-000000000444")
    chunk_id = UUID("00000000-0000-0000-0000-000000000555")

    class FakeCache:
        async def invalidate_project(self, project_id: str):
            invalidated.append(project_id)

    vector_store = FakeVectorStore()
    service = IngestionService(None, vector_store=vector_store, query_cache=FakeCache())  # type: ignore[arg-type]
    document = SimpleNamespace(
        id=document_id,
        project_id=project_id,
        tenant_id=tenant_id,
        status="indexed",
    )
    job = SimpleNamespace(id=job_id, document_id=document_id)
    chunk = SimpleNamespace(
        id=chunk_id,
        qdrant_point_id=UUID("00000000-0000-0000-0000-000000000123"),
    )

    async def fake_get_job(value):
        return job

    async def fake_get_document(value):
        return document

    async def fake_get_document_chunks(value):
        return [chunk]

    async def fake_soft_delete_document(target):
        target.status = "deleted"

    async def fake_archive_chunks(chunks):
        return None

    async def fake_commit():
        return None

    service.repository = SimpleNamespace(
        get_job=fake_get_job,
        get_document=fake_get_document,
        get_document_chunks=fake_get_document_chunks,
        soft_delete_document=fake_soft_delete_document,
        archive_chunks=fake_archive_chunks,
        commit=fake_commit,
    )

    await service.delete_ingestion_job(str(job_id))

    assert invalidated == [str(project_id)]


@pytest.mark.asyncio
async def test_create_ingestion_job_increments_document_version(monkeypatch):
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    previous_document_id = UUID("00000000-0000-0000-0000-000000000333")
    new_document_id = UUID("00000000-0000-0000-0000-000000000444")
    job_id = UUID("00000000-0000-0000-0000-000000000555")
    captured_create: dict[str, object] = {}

    service = IngestionService(None, dispatcher=FakeDispatcher())  # type: ignore[arg-type]

    async def fake_get_project(value):
        return SimpleNamespace(id=project_id, tenant_id=tenant_id)

    async def fake_get_latest_document_by_source_ref(project_id_value, source_ref):
        return SimpleNamespace(id=previous_document_id, version=2)

    async def fake_create_document(**kwargs):
        captured_create.update(kwargs)
        return SimpleNamespace(id=new_document_id)

    async def fake_create_job(**kwargs):
        return SimpleNamespace(id=job_id, status="pending")

    async def fake_commit():
        return None

    service.repository = SimpleNamespace(
        get_project=fake_get_project,
        get_latest_document_by_source_ref=fake_get_latest_document_by_source_ref,
        create_document=fake_create_document,
        create_job=fake_create_job,
        commit=fake_commit,
    )

    result = await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            mode="async",
        ),
        project_id,
    )

    assert result["document_id"] == str(new_document_id)
    assert captured_create["version"] == 3
    assert captured_create["previous_document_id"] == previous_document_id


@pytest.mark.asyncio
async def test_process_document_job_supersedes_previous_version(monkeypatch):
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    previous_document_id = UUID("00000000-0000-0000-0000-000000000333")
    current_document_id = UUID("00000000-0000-0000-0000-000000000444")
    archived_ids: list[str] = []
    deleted_point_ids: list[str] = []
    superseded_ids: list[str] = []

    async def fake_load(source_type, source_ref):
        return {
            "content": "Example article body",
            "metadata": {"title": "Example Article", "loader_strategy": "crawl4ai_rendered"},
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)

    service = IngestionService(None, vector_store=FakeVectorStore())  # type: ignore[arg-type]
    previous_document = SimpleNamespace(id=previous_document_id, project_id=project_id)
    previous_chunk = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000997"),
        qdrant_point_id=UUID("00000000-0000-0000-0000-000000000999"),
        parent_chunk_id=UUID("00000000-0000-0000-0000-000000000998"),
        modality="text",
        content_hash="old-hash",
        embed_model="gemini-old",
        embed_version="v1",
        dimension=3,
    )

    async def fake_update_document_status(document, status):
        document.status = status
        return document

    async def fake_update_job_status(*args, **kwargs):
        return None

    async def fake_commit():
        return None

    async def fake_create_chunks(rows):
        return [
            SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000701"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
            SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000702"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
        ]

    async def fake_attach_qdrant_point_ids(chunks, point_ids):
        return chunks

    async def fake_update_document_after_load(*args, **kwargs):
        return None

    async def fake_get_document(document_id):
        if document_id == previous_document_id:
            return previous_document
        return None

    async def fake_get_document_chunks(document_id):
        if document_id == previous_document_id:
            return [previous_chunk]
        return []

    async def fake_archive_chunks(chunks):
        archived_ids.extend(str(chunk.qdrant_point_id) for chunk in chunks if chunk.qdrant_point_id)
        return chunks

    async def fake_supersede_document(document):
        superseded_ids.append(str(document.id))
        return document

    async def fake_create_chunk_diff_logs(job_id, entries):
        return entries

    async def fake_delete_points(point_ids):
        deleted_point_ids.extend(point_ids)

    service.vector_store.delete_points = fake_delete_points  # type: ignore[method-assign]
    service.repository = SimpleNamespace(
        update_document_status=fake_update_document_status,
        update_job_status=fake_update_job_status,
        commit=fake_commit,
        create_chunks=fake_create_chunks,
        attach_qdrant_point_ids=fake_attach_qdrant_point_ids,
        update_document_after_load=fake_update_document_after_load,
        get_document=fake_get_document,
        get_document_chunks=fake_get_document_chunks,
        archive_chunks=fake_archive_chunks,
        supersede_document=fake_supersede_document,
        create_chunk_diff_logs=fake_create_chunk_diff_logs,
    )

    document = SimpleNamespace(
        id=current_document_id,
        tenant_id=tenant_id,
        project_id=project_id,
        source_type="web",
        source_ref="https://example.com/article",
        title="article",
        metadata_json={},
        previous_document_id=previous_document_id,
    )
    job = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000888"))

    await service._process_document_job(document, job, retry_count=0)

    assert superseded_ids == [str(previous_document_id)]
    assert archived_ids == ["00000000-0000-0000-0000-000000000999"]
    assert deleted_point_ids == ["00000000-0000-0000-0000-000000000999"]


@pytest.mark.asyncio
async def test_process_document_job_reuses_unchanged_chunk_vectors_and_writes_diff_logs(monkeypatch):
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    previous_document_id = UUID("00000000-0000-0000-0000-000000000333")
    current_document_id = UUID("00000000-0000-0000-0000-000000000444")
    embed_calls: list[str] = []
    diff_logs: list[dict[str, object]] = []
    upsert_rows: list[dict[str, object]] = []

    unchanged_text = "same body"
    changed_text = "new body"

    async def fake_load(source_type, source_ref):
        return {
            "content": f"{unchanged_text}\n{changed_text}",
            "metadata": {"title": "Example Article", "loader_strategy": "crawl4ai_rendered"},
            "chunk_count": 2,
        }

    async def fake_embed_text(content, title):
        embed_calls.append(content)
        return {"values": [0.9, 0.8], "model": "gemini-test", "dimension": 2}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "build_chunks",
        lambda source_type, content, metadata: [
            {"content": unchanged_text},
            {"content": changed_text},
        ],
        raising=False,
    )

    class DiffVectorStore(FakeVectorStore):
        async def fetch_dense_vectors(self, point_ids: list[str]) -> dict[str, list[float]]:
            return {"00000000-0000-0000-0000-00000000aaaa": [0.1, 0.2]}

        async def upsert_chunks(self, chunks: list[dict[str, object]]) -> list[str]:
            upsert_rows.extend(chunks)
            return [f"00000000-0000-0000-0000-{index + 1:012d}" for index, _ in enumerate(chunks)]

    service = IngestionService(None, vector_store=DiffVectorStore())  # type: ignore[arg-type]
    previous_child = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000551"),
        parent_chunk_id=UUID("00000000-0000-0000-0000-000000000550"),
        modality="text",
        content_hash=service._content_hash(unchanged_text),
        content=unchanged_text,
        qdrant_point_id=UUID("00000000-0000-0000-0000-00000000aaaa"),
        embed_model="gemini-old",
        embed_version="v1",
        dimension=2,
    )
    deleted_previous_child = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000661"),
        parent_chunk_id=UUID("00000000-0000-0000-0000-000000000660"),
        modality="text",
        content_hash=service._content_hash("deleted body"),
        content="deleted body",
        qdrant_point_id=UUID("00000000-0000-0000-0000-00000000bbbb"),
        embed_model="gemini-old",
        embed_version="v1",
        dimension=2,
    )

    created_chunks = [
        SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000701"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
        SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000702"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
        SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000703"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
        SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000704"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
    ]

    async def fake_update_document_status(document, status):
        document.status = status
        return document

    async def fake_update_job_status(*args, **kwargs):
        return None

    async def fake_commit():
        return None

    async def fake_create_chunks(rows):
        return created_chunks

    async def fake_attach_qdrant_point_ids(chunks, point_ids):
        return chunks

    async def fake_update_document_after_load(*args, **kwargs):
        return None

    async def fake_get_document(document_id):
        if document_id == previous_document_id:
            return SimpleNamespace(id=previous_document_id, project_id=project_id)
        return None

    async def fake_get_document_chunks(document_id):
        if document_id == previous_document_id:
            return [previous_child, deleted_previous_child]
        return []

    async def fake_archive_chunks(chunks):
        return chunks

    async def fake_supersede_document(document):
        return document

    async def fake_create_chunk_diff_logs(job_id, entries):
        diff_logs.extend(entries)
        return entries

    async def fake_delete_points(point_ids):
        return None

    service.vector_store.delete_points = fake_delete_points  # type: ignore[method-assign]
    service.repository = SimpleNamespace(
        update_document_status=fake_update_document_status,
        update_job_status=fake_update_job_status,
        commit=fake_commit,
        create_chunks=fake_create_chunks,
        attach_qdrant_point_ids=fake_attach_qdrant_point_ids,
        update_document_after_load=fake_update_document_after_load,
        get_document=fake_get_document,
        get_document_chunks=fake_get_document_chunks,
        archive_chunks=fake_archive_chunks,
        supersede_document=fake_supersede_document,
        create_chunk_diff_logs=fake_create_chunk_diff_logs,
    )

    document = SimpleNamespace(
        id=current_document_id,
        tenant_id=tenant_id,
        project_id=project_id,
        source_type="web",
        source_ref="https://example.com/article",
        title="article",
        metadata_json={},
        previous_document_id=previous_document_id,
    )
    job = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000888"))

    await service._process_document_job(document, job, retry_count=0)

    assert embed_calls == [changed_text]
    assert upsert_rows[0]["vector"] == [0.1, 0.2]
    assert upsert_rows[1]["vector"] == [0.9, 0.8]
    assert {entry["operation"] for entry in diff_logs} == {"unchanged", "modified", "deleted"}


@pytest.mark.asyncio
async def test_create_ingestion_job_persists_source_connector_id(monkeypatch):
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    connector_id = UUID("00000000-0000-0000-0000-000000000333")
    captured_create: dict[str, object] = {}

    service = IngestionService(None, dispatcher=FakeDispatcher())  # type: ignore[arg-type]

    async def fake_get_project(value):
        return SimpleNamespace(id=project_id, tenant_id=tenant_id)

    async def fake_get_latest_document_by_source_ref(project_id_value, source_ref):
        return None

    async def fake_create_document(**kwargs):
        captured_create.update(kwargs)
        return SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000444"))

    async def fake_create_job(**kwargs):
        return SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000555"), status="pending")

    async def fake_commit():
        return None

    service.repository = SimpleNamespace(
        get_project=fake_get_project,
        get_latest_document_by_source_ref=fake_get_latest_document_by_source_ref,
        create_document=fake_create_document,
        create_job=fake_create_job,
        commit=fake_commit,
    )

    await service.create_ingestion_job(
        IngestRequest(
            source_type="web",
            source_ref="https://example.com/article",
            source_connector_id=str(connector_id),
            cursor_state={"cursor": "abc"},
            mode="async",
        ),
        project_id,
    )

    assert captured_create["source_connector_id"] == connector_id
    assert captured_create["metadata"]["cursor_state"] == {"cursor": "abc"}


@pytest.mark.asyncio
async def test_process_document_job_upserts_sync_checkpoint(monkeypatch):
    project_id = UUID("00000000-0000-0000-0000-000000000111")
    tenant_id = UUID("00000000-0000-0000-0000-000000000222")
    connector_id = UUID("00000000-0000-0000-0000-000000000333")
    checkpoint_calls: list[tuple[UUID, dict[str, object]]] = []

    async def fake_load(source_type, source_ref):
        return {
            "content": "Example article body",
            "metadata": {"title": "Example Article", "loader_strategy": "crawl4ai_rendered"},
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        return {"values": [0.1, 0.2, 0.3], "model": "gemini-test", "dimension": 3}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)

    service = IngestionService(None, vector_store=FakeVectorStore())  # type: ignore[arg-type]

    async def fake_update_document_status(document, status):
        document.status = status
        return document

    async def fake_update_job_status(*args, **kwargs):
        return None

    async def fake_commit():
        return None

    async def fake_create_chunks(rows):
        return [
            SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000701"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
            SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000702"), modality="text", acl=[], page_number=None, qdrant_point_id=None),
        ]

    async def fake_attach_qdrant_point_ids(chunks, point_ids):
        return chunks

    async def fake_update_document_after_load(*args, **kwargs):
        return None

    async def fake_create_chunk_diff_logs(job_id, entries):
        return entries

    async def fake_upsert_sync_checkpoint(source_connector_id, cursor_state):
        checkpoint_calls.append((source_connector_id, cursor_state))
        return None

    service.repository = SimpleNamespace(
        update_document_status=fake_update_document_status,
        update_job_status=fake_update_job_status,
        commit=fake_commit,
        create_chunks=fake_create_chunks,
        attach_qdrant_point_ids=fake_attach_qdrant_point_ids,
        update_document_after_load=fake_update_document_after_load,
        create_chunk_diff_logs=fake_create_chunk_diff_logs,
        get_document=lambda document_id: None,
        get_document_chunks=lambda document_id: [],
        archive_chunks=lambda chunks: chunks,
        supersede_document=lambda document: document,
        upsert_sync_checkpoint=fake_upsert_sync_checkpoint,
    )

    document = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000444"),
        tenant_id=tenant_id,
        project_id=project_id,
        source_type="web",
        source_ref="https://example.com/article",
        title="article",
        metadata_json={"cursor_state": {"cursor": "abc"}},
        source_connector_id=connector_id,
        previous_document_id=None,
        content_hash="hash-before-update",
    )
    job = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000888"))

    await service._process_document_job(document, job, retry_count=0)

    assert checkpoint_calls == [
        (
            connector_id,
            {
                "cursor": "abc",
                "document_id": "00000000-0000-0000-0000-000000000444",
                "source_ref": "https://example.com/article",
                "content_hash": service._content_hash("Example article body"),
            },
        )
    ]


@pytest.mark.asyncio
async def test_requeue_stale_documents_enqueues_latest_indexed_document(
    integration_session,
    seeded_project,
):
    dispatcher = FakeDispatcher()
    service = IngestionService(integration_session, dispatcher=dispatcher, vector_store=FakeVectorStore())
    repository = service.repository

    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/stale",
        status="indexed",
        title="Stale Doc",
        content_hash=service._content_hash("https://example.com/stale"),
        metadata={},
        version=1,
    )
    await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "modality": "text",
                "content": "Parent",
                "content_hash": service._content_hash("Parent"),
                "token_count": 1,
                "section_title": "Stale Doc",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "modality": "text",
                "content": "Child chunk",
                "content_hash": service._content_hash("Child chunk"),
                "token_count": 2,
                "section_title": "Stale Doc",
                "acl": [],
                "embed_model": "gemini-old",
                "embed_version": "gemini-old-768",
                "dimension": 3,
            },
        ]
    )
    await repository.commit()

    result = await service.requeue_stale_documents()

    assert result == {"stale_document_count": 1}
    assert len(dispatcher.enqueued) == 1
    latest_document = await repository.get_latest_document_by_source_ref(
        seeded_project["project_id"],
        "https://example.com/stale",
    )
    assert latest_document is not None
    assert latest_document.version == 2
    assert latest_document.status == "pending"


@pytest.mark.asyncio
async def test_requeue_stale_documents_skips_current_embed_version(
    integration_session,
    seeded_project,
):
    dispatcher = FakeDispatcher()
    service = IngestionService(integration_session, dispatcher=dispatcher, vector_store=FakeVectorStore())
    repository = service.repository
    settings = get_settings()
    current_embed_version = f"{settings.embed_model}-{settings.embed_dimension}"

    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/current",
        status="indexed",
        title="Current Doc",
        content_hash=service._content_hash("https://example.com/current"),
        metadata={},
        version=1,
    )
    await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "modality": "text",
                "content": "Parent",
                "content_hash": service._content_hash("Parent"),
                "token_count": 1,
                "section_title": "Current Doc",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "modality": "text",
                "content": "Child chunk",
                "content_hash": service._content_hash("Child chunk"),
                "token_count": 2,
                "section_title": "Current Doc",
                "acl": [],
                "embed_model": settings.embed_model,
                "embed_version": current_embed_version,
                "dimension": settings.embed_dimension,
            },
        ]
    )
    await repository.commit()

    result = await service.requeue_stale_documents()

    assert result == {"stale_document_count": 0}
    assert dispatcher.enqueued == []


@pytest.mark.asyncio
async def test_process_document_job_skips_semantic_duplicate_chunk(monkeypatch):
    embed_calls: list[str] = []
    upsert_rows: list[dict[str, object]] = []

    async def fake_load(source_type, source_ref):
        return {
            "content": "Alpha chunk. Beta chunk.",
            "metadata": {"title": "Example Article", "content_length": 24},
            "chunk_count": 1,
        }

    async def fake_embed_text(content, title):
        embed_calls.append(content)
        if content == "Alpha chunk.":
            return {"values": [0.1, 0.2], "model": "gemini-test", "embed_version": "gemini-test-2", "dimension": 2}
        return {"values": [0.9, 0.8], "model": "gemini-test", "embed_version": "gemini-test-2", "dimension": 2}

    monkeypatch.setattr(ingestion_service_module, "load_source", fake_load, raising=False)
    monkeypatch.setattr(ingestion_service_module, "embed_text_content", fake_embed_text, raising=False)
    monkeypatch.setattr(
        ingestion_service_module,
        "build_chunks",
        lambda *args, **kwargs: [
            {"content": "Alpha chunk.", "page_number": None, "bbox": None},
            {"content": "Beta chunk.", "page_number": None, "bbox": None},
        ],
        raising=False,
    )

    class DedupVectorStore(FakeVectorStore):
        async def find_semantic_duplicate(self, **kwargs):
            if kwargs["query_vector"] == [0.9, 0.8]:
                return {"document_id": "doc-existing", "chunk_id": "chunk-existing", "score": 0.99}
            return None

        async def upsert_chunks(self, chunks):
            upsert_rows.extend(chunks)
            return await super().upsert_chunks(chunks)

    service = IngestionService(None, vector_store=DedupVectorStore())  # type: ignore[arg-type]

    async def fake_update_document_status(document, status):
        document.status = status
        return document

    async def fake_update_job_status(*args, **kwargs):
        return None

    async def fake_commit():
        return None

    async def fake_create_chunks(rows):
        return [
            SimpleNamespace(
                id=UUID(f"00000000-0000-0000-0000-{index + 701:012d}"),
                modality=row["modality"],
                acl=row.get("acl", []),
                page_number=row.get("page_number"),
                qdrant_point_id=None,
            )
            for index, row in enumerate(rows)
        ]

    async def fake_attach_qdrant_point_ids(chunks, point_ids):
        return chunks

    async def fake_update_document_after_load(*args, **kwargs):
        return None

    async def fake_create_chunk_diff_logs(job_id, entries):
        return entries

    service.repository = SimpleNamespace(
        update_document_status=fake_update_document_status,
        update_job_status=fake_update_job_status,
        commit=fake_commit,
        create_chunks=fake_create_chunks,
        attach_qdrant_point_ids=fake_attach_qdrant_point_ids,
        update_document_after_load=fake_update_document_after_load,
        create_chunk_diff_logs=fake_create_chunk_diff_logs,
        get_document=lambda document_id: None,
        get_document_chunks=lambda document_id: [],
        archive_chunks=lambda chunks: chunks,
        supersede_document=lambda document: document,
        upsert_sync_checkpoint=lambda *args, **kwargs: None,
    )

    document = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000444"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000222"),
        project_id=UUID("00000000-0000-0000-0000-000000000111"),
        source_type="web",
        source_ref="https://example.com/article",
        title="article",
        metadata_json={},
        previous_document_id=None,
        content_hash="hash-before-update",
    )
    job = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000888"))

    await service._process_document_job(document, job, retry_count=0)

    assert embed_calls == ["Alpha chunk.", "Beta chunk."]
    assert len(upsert_rows) == 1
    assert upsert_rows[0]["content"] == "Alpha chunk."
