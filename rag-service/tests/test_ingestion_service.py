import pytest
from uuid import UUID
from fastapi import HTTPException

from app.models.db import RagChunk
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

    async def ensure_collection(self) -> None:
        return None

    async def upsert_chunks(self, chunks: list[dict[str, object]]) -> list[str]:
        return [f"00000000-0000-0000-0000-{index + 1:012d}" for index, _ in enumerate(chunks)]

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
