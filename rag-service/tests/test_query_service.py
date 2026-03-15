from uuid import UUID

import pytest

from app.repositories.ingestion import IngestionRepository
from app.services import query as query_module
from app.services.query import QueryService


@pytest.mark.asyncio
async def test_query_service_answers_from_indexed_documents(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/q1-report",
        status="indexed",
        title="Q1 Report",
        content_hash="hash-1",
        metadata={
            "content_text": "Revenue grew sharply in Q1 due to subscription sales.",
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/team-update",
        status="indexed",
        title="Team Update",
        content_hash="hash-2",
        metadata={
            "content_text": "Hiring plan and team notes.",
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question(
        "Revenue in Q1?",
        seeded_project["project_id"],
    )

    assert "Revenue grew sharply in Q1" in result["answer"]
    assert result["retrieval_mode"] == "metadata_fallback"
    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Q1 Report"
    assert result["sources"][0]["document_id"] != ""


@pytest.mark.asyncio
async def test_query_service_uses_query_embedding_task(monkeypatch, integration_session, seeded_project):
    captured: dict[str, str] = {}

    async def fake_embed_query_text(question: str):
        captured["question"] = question
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    service = QueryService(integration_session)
    await service.answer_question("Revenue in Q1?", seeded_project["project_id"])

    assert captured["question"] == "Revenue in Q1?"


@pytest.mark.asyncio
async def test_query_service_filters_by_scope_id(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Customer 42 Snapshot",
        content_hash="hash-structured-1",
        metadata={
            "content_text": "Acme Mobilya negotiation details and revenue outlook.",
            "scope_type": "customer",
            "scope_id": "cust_42",
            "tags": ["crm", "daily-sync"],
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Customer 77 Snapshot",
        content_hash="hash-structured-2",
        metadata={
            "content_text": "Beta Yapi stalled deal details and risk summary.",
            "scope_type": "customer",
            "scope_id": "cust_77",
            "tags": ["crm", "daily-sync"],
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question(
        "negotiation details",
        seeded_project["project_id"],
        scope_type="customer",
        scope_id="cust_42",
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Customer 42 Snapshot"


@pytest.mark.asyncio
async def test_query_service_filters_by_tags(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="CRM Record",
        content_hash="hash-tag-1",
        metadata={
            "content_text": "Customer opportunity and sales notes.",
            "tags": ["crm", "daily-sync"],
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Diet Record",
        content_hash="hash-tag-2",
        metadata={
            "content_text": "Daily calorie intake and hydration notes.",
            "tags": ["diet", "daily-sync"],
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question(
        "daily notes",
        seeded_project["project_id"],
        tags=["diet"],
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Diet Record"


@pytest.mark.asyncio
async def test_query_service_filters_by_entity_id(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Customer Snapshot",
        content_hash="hash-entity-1",
        metadata={
            "content_text": "Acme customer summary and opportunity details.",
            "entity_id": "cust_42",
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Another Customer Snapshot",
        content_hash="hash-entity-2",
        metadata={
            "content_text": "Beta customer summary and churn risk details.",
            "entity_id": "cust_77",
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question(
        "customer summary",
        seeded_project["project_id"],
        entity_id="cust_42",
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Customer Snapshot"


@pytest.mark.asyncio
async def test_query_service_filters_by_snapshot_date(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Snapshot March 15",
        content_hash="hash-snapshot-1",
        metadata={
            "content_text": "March 15 pipeline summary and revenue status.",
            "snapshot_date": "2026-03-15",
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Snapshot March 14",
        content_hash="hash-snapshot-2",
        metadata={
            "content_text": "March 14 pipeline summary and revenue status.",
            "snapshot_date": "2026-03-14",
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question(
        "pipeline summary",
        seeded_project["project_id"],
        snapshot_date="2026-03-15",
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Snapshot March 15"


@pytest.mark.asyncio
async def test_query_service_uses_qdrant_payload_filter_for_metadata_candidates(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    captured: dict[str, object] = {}

    class FakeVectorStore:
        async def search_chunks(
            self,
            *,
            query_vector,
            tenant_id,
            scope_type,
            scope_id,
            entity_id,
            snapshot_date,
            tags,
            limit,
        ):
            captured["tenant_id"] = tenant_id
            captured["scope_type"] = scope_type
            captured["scope_id"] = scope_id
            captured["entity_id"] = entity_id
            captured["snapshot_date"] = snapshot_date
            captured["tags"] = tags
            captured["limit"] = limit
            return [{"document_id": str(matching_document.id), "chunk_id": "chunk-1", "score": 0.92}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    matching_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Customer Snapshot",
        content_hash="hash-filter-hit",
        metadata={
            "content_text": "Acme customer summary and opportunity details.",
            "scope_type": "customer",
            "scope_id": "cust_42",
            "entity_id": "cust_42",
            "snapshot_date": "2026-03-15",
            "tags": ["crm", "daily-sync"],
        },
    )
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Other Customer Snapshot",
        content_hash="hash-filter-miss",
        metadata={
            "content_text": "Beta customer summary and churn risk details.",
            "scope_type": "customer",
            "scope_id": "cust_77",
            "entity_id": "cust_77",
            "snapshot_date": "2026-03-14",
            "tags": ["crm", "daily-sync"],
        },
    )
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question(
        "customer summary",
        seeded_project["project_id"],
        scope_type="customer",
        scope_id="cust_42",
        entity_id="cust_42",
        snapshot_date="2026-03-15",
        tags=["crm"],
    )

    assert captured == {
        "tenant_id": str(seeded_project["tenant_id"]),
        "scope_type": "customer",
        "scope_id": "cust_42",
        "entity_id": "cust_42",
        "snapshot_date": "2026-03-15",
        "tags": ["crm"],
        "limit": 6,
    }
    assert len(result["sources"]) == 1
    assert result["sources"][0]["title"] == "Customer Snapshot"


@pytest.mark.asyncio
async def test_query_service_uses_qdrant_semantic_ranking_order(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.11, 0.22],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    class FakeVectorStore:
        async def search_chunks(
            self,
            *,
            query_vector,
            tenant_id,
            scope_type,
            scope_id,
            entity_id,
            snapshot_date,
            tags,
            limit,
        ):
            assert query_vector == [0.11, 0.22]
            assert tenant_id == str(seeded_project["tenant_id"])
            assert limit == 6
            return [
                {"document_id": str(semantic_doc.id), "chunk_id": "chunk-semantic", "score": 0.99},
                {"document_id": str(keyword_doc.id), "chunk_id": "chunk-keyword", "score": 0.75},
            ]

        async def filter_document_ids(self, *, tenant_id, scope_type, scope_id, entity_id, snapshot_date, tags):
            return [str(semantic_doc.id), str(keyword_doc.id)]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    keyword_doc = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Keyword Match",
        content_hash="hash-keyword",
        metadata={
            "content_text": "Revenue keyword appears here but this should rank second.",
        },
    )
    semantic_doc = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Semantic Match",
        content_hash="hash-semantic",
        metadata={
            "content_text": "This text has no literal keyword overlap but should rank first semantically.",
        },
    )
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question("revenue growth", seeded_project["project_id"])

    assert [source["title"] for source in result["sources"]] == ["Semantic Match", "Keyword Match"]


@pytest.mark.asyncio
async def test_query_service_builds_sources_from_retrieved_chunk_content(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.31, 0.42],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    class FakeVectorStore:
        async def search_chunks(
            self,
            *,
            query_vector,
            tenant_id,
            scope_type,
            scope_id,
            entity_id,
            snapshot_date,
            tags,
            limit,
        ):
            return [
                {"document_id": str(document.id), "chunk_id": str(chunk.id), "score": 0.98},
            ]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Chunked Customer Snapshot",
        content_hash="hash-chunked-doc",
        metadata={
            "content_text": "Generic document summary that should not be used for snippets.",
        },
    )
    chunks = await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "chunk-parent",
                "content": "Parent chunk content.",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "Customer Summary",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "chunk-child",
                "content": "Customer prefers quarterly billing and requested a renewal quote last week.",
                "modality": "text",
                "token_count": 10,
                "page_number": 3,
                "bbox": None,
                "section_title": "Customer Summary",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    chunk = chunks[1]
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question("renewal quote", seeded_project["project_id"])

    assert result["answer"] == (
        "Chunked Customer Snapshot: Parent chunk content. "
        "Customer prefers quarterly billing and requested a renewal quote last week."
    )
    assert result["retrieval_mode"] == "semantic_qdrant"
    assert result["retrieval_context"] == [
        {
            "title": "Chunked Customer Snapshot",
            "snippet": "Customer prefers quarterly billing and requested a renewal quote last week.",
            "parent_context": "Parent chunk content.",
            "score": 0.98,
        }
    ]
    assert result["sources"] == [
        {
            "document_id": str(document.id),
            "title": "Chunked Customer Snapshot",
            "source_ref": "inline://structured-records",
            "snippet": "Customer prefers quarterly billing and requested a renewal quote last week.",
            "chunk_id": str(chunk.id),
            "page_number": 3,
            "section_title": "Customer Summary",
            "parent_context": "Parent chunk content.",
            "score": 0.98,
        }
    ]


@pytest.mark.asyncio
async def test_query_service_returns_empty_mode_when_no_documents(
    integration_session,
    seeded_project,
    monkeypatch,
):
    async def fake_embed_query_text(question: str):
        return {
            "task_type": "RETRIEVAL_QUERY",
            "values": [0.1, 0.2],
            "model": "gemini-embedding-2",
            "dimension": 2,
        }

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    service = QueryService(integration_session)
    result = await service.answer_question("missing context", seeded_project["project_id"])

    assert result["retrieval_mode"] == "empty"
    assert result["sources"] == []
    assert result["retrieval_context"] == []
