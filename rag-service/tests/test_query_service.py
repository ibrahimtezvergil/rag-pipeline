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
async def test_query_service_generates_answer_from_final_sources(
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

    def fake_build_query_answer_prompt(*, question: str, sources: list[dict[str, object]]) -> str:
        captured["question"] = question
        captured["sources"] = sources
        return "PROMPT"

    async def fake_generate(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Generated answer"

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)
    monkeypatch.setattr(
        query_module,
        "build_query_answer_prompt",
        fake_build_query_answer_prompt,
        raising=False,
    )
    monkeypatch.setattr(query_module, "generate_text", fake_generate, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/q1-report",
        status="indexed",
        title="Q1 Report",
        content_hash="hash-generated-1",
        metadata={
            "content_text": "Revenue grew sharply in Q1 due to subscription sales.",
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question("Revenue in Q1?", seeded_project["project_id"])

    assert result["answer"] == "Generated answer"
    assert captured["question"] == "Revenue in Q1?"
    assert captured["prompt"] == "PROMPT"
    assert captured["sources"]
    assert "query_embedding" not in result


@pytest.mark.asyncio
async def test_query_service_returns_empty_without_calling_llm(
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

    async def fake_generate(prompt: str) -> str:
        raise AssertionError("llm.generate should not be called for empty retrieval")

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)
    monkeypatch.setattr(query_module, "generate_text", fake_generate, raising=False)

    service = QueryService(integration_session)
    result = await service.answer_question("Unknown question", seeded_project["project_id"])

    assert result["retrieval_mode"] == "empty"
    assert result["answer"] == "Bu proje icin sorgulanabilir indexed dokuman bulunamadi."
    assert "query_embedding" not in result


@pytest.mark.asyncio
async def test_query_service_falls_back_when_llm_generate_raises(
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

    def fake_build_query_answer_prompt(*, question: str, sources: list[dict[str, object]]) -> str:
        return "PROMPT"

    async def fake_generate(prompt: str) -> str:
        raise RuntimeError("provider failure")

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)
    monkeypatch.setattr(
        query_module,
        "build_query_answer_prompt",
        fake_build_query_answer_prompt,
        raising=False,
    )
    monkeypatch.setattr(query_module, "generate_text", fake_generate, raising=False)

    repository = IngestionRepository(integration_session)
    await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="web",
        source_ref="https://example.com/q1-report",
        status="indexed",
        title="Q1 Report",
        content_hash="hash-fallback-1",
        metadata={
            "content_text": "Revenue grew sharply in Q1 due to subscription sales.",
        },
    )
    await repository.commit()

    service = QueryService(integration_session)
    result = await service.answer_question("Revenue in Q1?", seeded_project["project_id"])

    assert "Revenue grew sharply in Q1" in result["answer"]
    assert result["sources"][0]["title"] == "Q1 Report"


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

    assert result["retrieval_mode"] == "hybrid_rrf"
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
    assert result["retrieval_mode"] == "hybrid_rrf"
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
            "resolved_chunk_id": str(chunks[0].id),
            "page_number": 3,
            "section_title": "Customer Summary",
            "parent_context": "Parent chunk content.",
            "score": 0.98,
            "acl": [],
        }
    ]


@pytest.mark.asyncio
async def test_query_service_resolves_child_hit_to_parent_context_block(
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
        async def search_chunks(self, **kwargs):
            return [{"document_id": str(document.id), "chunk_id": str(child.id), "score": 0.98}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Parent Resolver",
        content_hash="resolver-doc",
        metadata={"content_text": "ignored"},
    )
    chunks = await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "resolver-parent",
                "content": "Parent policy summary",
                "modality": "text",
                "token_count": 3,
                "page_number": 1,
                "bbox": None,
                "section_title": "Policy",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "resolver-child",
                "content": "Refund window is 30 days for annual plans.",
                "modality": "text",
                "token_count": 8,
                "page_number": 1,
                "bbox": None,
                "section_title": "Policy",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    parent = chunks[0]
    child = chunks[1]
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question("refund window", seeded_project["project_id"])

    assert result["sources"][0]["chunk_id"] == str(child.id)
    assert result["sources"][0]["resolved_chunk_id"] == str(parent.id)
    assert result["retrieval_context"][0]["title"] == "Parent Resolver"
    assert result["retrieval_context"][0]["parent_context"] == "Parent policy summary"


@pytest.mark.asyncio
async def test_query_service_uses_sparse_qdrant_when_requested(
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

    captured: dict[str, object] = {}

    class FakeVectorStore:
        async def search_sparse_chunks(
            self,
            *,
            sparse_query,
            tenant_id,
            scope_type,
            scope_id,
            entity_id,
            snapshot_date,
            tags,
            limit,
        ):
            captured["sparse_query"] = sparse_query
            captured["tenant_id"] = tenant_id
            captured["limit"] = limit
            return [{"document_id": str(document.id), "chunk_id": str(chunk.id), "score": 2.4}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Sparse Customer Snapshot",
        content_hash="hash-sparse-doc",
        metadata={
            "content_text": "renewal quote pending and billing frequency changed",
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
                "content": "renewal quote pending and billing frequency changed",
                "modality": "text",
                "token_count": 7,
                "page_number": None,
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
    result = await service.answer_question(
        "renewal billing",
        seeded_project["project_id"],
        retrieval_mode="sparse",
    )

    assert captured["tenant_id"] == str(seeded_project["tenant_id"])
    assert captured["limit"] == 6
    assert captured["sparse_query"]["indices"]
    assert result["retrieval_mode"] == "sparse_qdrant"
    assert result["sources"][0]["chunk_id"] == str(chunk.id)


@pytest.mark.asyncio
async def test_query_service_uses_hybrid_rrf_by_default(
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
                {"document_id": str(dense_document.id), "chunk_id": str(dense_chunk.id), "score": 0.99},
                {"document_id": str(shared_document.id), "chunk_id": str(shared_chunk.id), "score": 0.85},
            ]

        async def search_sparse_chunks(
            self,
            *,
            sparse_query,
            tenant_id,
            scope_type,
            scope_id,
            entity_id,
            snapshot_date,
            tags,
            limit,
        ):
            return [
                {"document_id": str(shared_document.id), "chunk_id": str(shared_chunk.id), "score": 3.2},
                {"document_id": str(sparse_document.id), "chunk_id": str(sparse_chunk.id), "score": 2.9},
            ]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    dense_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Dense Winner",
        content_hash="hash-dense-doc",
        metadata={"content_text": "semantic revenue growth outlook"},
    )
    shared_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Hybrid Shared Winner",
        content_hash="hash-shared-doc",
        metadata={"content_text": "renewal billing revenue growth"},
    )
    sparse_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Sparse Winner",
        content_hash="hash-sparse-doc-2",
        metadata={"content_text": "renewal billing pending"},
    )
    chunks = await repository.create_chunks(
        [
            {
                "document_id": dense_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "dense-parent",
                "content": "dense parent",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "Dense",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": dense_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "dense-child",
                "content": "semantic revenue growth outlook",
                "modality": "text",
                "token_count": 4,
                "page_number": None,
                "bbox": None,
                "section_title": "Dense",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": shared_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "shared-parent",
                "content": "shared parent",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "Shared",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": shared_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "shared-child",
                "content": "renewal billing revenue growth",
                "modality": "text",
                "token_count": 4,
                "page_number": None,
                "bbox": None,
                "section_title": "Shared",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": sparse_document.id,
                "chunk_index": 4,
                "parent_chunk_id": None,
                "content_hash": "sparse-parent",
                "content": "sparse parent",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "Sparse",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": sparse_document.id,
                "chunk_index": 5,
                "parent_chunk_id": "__PARENT_INDEX__:4",
                "content_hash": "sparse-child",
                "content": "renewal billing pending",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "Sparse",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    dense_chunk = chunks[1]
    shared_chunk = chunks[3]
    sparse_chunk = chunks[5]
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question("renewal revenue", seeded_project["project_id"])

    assert result["retrieval_mode"] == "hybrid_rrf"
    assert [source["title"] for source in result["sources"]] == [
        "Hybrid Shared Winner",
        "Dense Winner",
        "Sparse Winner",
    ]
    assert result["sources"][0]["chunk_id"] == str(shared_chunk.id)


@pytest.mark.asyncio
async def test_query_service_reranks_hybrid_candidates_when_enabled(
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
        async def search_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.99},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.97},
            ]

        async def search_sparse_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 2.0},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 1.9},
            ]

    class FakeReranker:
        async def rerank(self, *, query, documents, top_n):
            assert query == "renewal billing"
            assert len(documents) == 2
            assert top_n == 2
            return [{"index": 1, "score": 0.93}, {"index": 0, "score": 0.51}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    first_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="First Candidate",
        content_hash="rerank-doc-1",
        metadata={"content_text": "renewal timeline update"},
    )
    second_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Second Candidate",
        content_hash="rerank-doc-2",
        metadata={"content_text": "billing issue summary"},
    )
    chunks = await repository.create_chunks(
        [
            {
                "document_id": first_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "first-parent",
                "content": "parent one",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": first_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "first-child",
                "content": "renewal timeline update",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "second-parent",
                "content": "parent two",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "second-child",
                "content": "billing issue summary",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    first_chunk = chunks[1]
    second_chunk = chunks[3]
    project = await integration_session.get(query_module.RagProject, seeded_project["project_id"])
    project.config = {"use_reranker": True}
    await integration_session.commit()

    service = QueryService(
        integration_session,
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
    )
    result = await service.answer_question("renewal billing", seeded_project["project_id"])

    assert result["retrieval_mode"] == "hybrid_rrf_rerank"
    assert [source["title"] for source in result["sources"]] == ["Second Candidate", "First Candidate"]
    assert result["sources"][0]["score"] == 0.93


@pytest.mark.asyncio
async def test_query_service_falls_back_when_reranker_fails(
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
        async def search_chunks(self, **kwargs):
            return [{"document_id": str(document.id), "chunk_id": str(chunk.id), "score": 0.99}]

        async def search_sparse_chunks(self, **kwargs):
            return [{"document_id": str(document.id), "chunk_id": str(chunk.id), "score": 1.1}]

    class FailingReranker:
        async def rerank(self, *, query, documents, top_n):
            raise query_module.httpx.HTTPError("cohere unavailable")

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-records",
        status="indexed",
        title="Fallback Candidate",
        content_hash="rerank-fallback",
        metadata={"content_text": "renewal quote pending"},
    )
    chunks = await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "fallback-parent",
                "content": "parent",
                "modality": "text",
                "token_count": 1,
                "page_number": None,
                "bbox": None,
                "section_title": "X",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "fallback-child",
                "content": "renewal quote pending",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "X",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    chunk = chunks[1]
    project = await integration_session.get(query_module.RagProject, seeded_project["project_id"])
    project.config = {"use_reranker": True}
    await integration_session.commit()

    service = QueryService(
        integration_session,
        vector_store=FakeVectorStore(),
        reranker=FailingReranker(),
    )
    result = await service.answer_question("renewal", seeded_project["project_id"])

    assert result["retrieval_mode"] == "hybrid_rrf"
    assert result["sources"][0]["chunk_id"] == str(chunk.id)


@pytest.mark.asyncio
async def test_query_service_applies_project_top_k_to_final_sources(
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
        async def search_chunks(self, **kwargs):
            return [
                {"document_id": str(documents[0].id), "chunk_id": str(chunks[0].id), "score": 0.99},
                {"document_id": str(documents[1].id), "chunk_id": str(chunks[1].id), "score": 0.97},
                {"document_id": str(documents[2].id), "chunk_id": str(chunks[2].id), "score": 0.95},
            ]

        async def search_sparse_chunks(self, **kwargs):
            return [
                {"document_id": str(documents[0].id), "chunk_id": str(chunks[0].id), "score": 2.4},
                {"document_id": str(documents[1].id), "chunk_id": str(chunks[1].id), "score": 2.3},
                {"document_id": str(documents[2].id), "chunk_id": str(chunks[2].id), "score": 2.2},
            ]

    class FakeReranker:
        async def rerank(self, *, query, documents, top_n):
            assert top_n == 2
            return [{"index": 2, "score": 0.93}, {"index": 1, "score": 0.72}, {"index": 0, "score": 0.51}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    documents = []
    for idx in range(3):
        document = await repository.create_document(
            project_id=seeded_project["project_id"],
            tenant_id=seeded_project["tenant_id"],
            source_type="structured",
            source_ref=f"inline://structured-{idx}",
            status="indexed",
            title=f"Candidate {idx + 1}",
            content_hash=f"topk-{idx}",
            metadata={"content_text": f"candidate text {idx + 1}"},
        )
        documents.append(document)
    created_chunks = await repository.create_chunks(
        [
            {
                "document_id": document.id,
                "chunk_index": idx * 2,
                "parent_chunk_id": None,
                "content_hash": f"parent-{idx}",
                "content": f"parent {idx}",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "S",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            }
            for idx, document in enumerate(documents)
        ]
        + [
            {
                "document_id": document.id,
                "chunk_index": idx * 2 + 1,
                "parent_chunk_id": f"__PARENT_INDEX__:{idx * 2}",
                "content_hash": f"child-{idx}",
                "content": f"candidate text {idx + 1}",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "S",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            }
            for idx, document in enumerate(documents)
        ]
    )
    chunks = [created_chunks[3], created_chunks[4], created_chunks[5]]
    project = await integration_session.get(query_module.RagProject, seeded_project["project_id"])
    project.config = {"top_k": 2, "rerank_top_n": 2}
    await integration_session.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore(), reranker=FakeReranker())
    result = await service.answer_question("candidate", seeded_project["project_id"])

    assert len(result["sources"]) == 2


@pytest.mark.asyncio
async def test_query_service_applies_score_threshold_with_minimum_one_result(
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
        async def search_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.99},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.97},
            ]

        async def search_sparse_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.01},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.009},
            ]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    first_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-a",
        status="indexed",
        title="Threshold A",
        content_hash="threshold-a",
        metadata={"content_text": "threshold document a"},
    )
    second_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://structured-b",
        status="indexed",
        title="Threshold B",
        content_hash="threshold-b",
        metadata={"content_text": "threshold document b"},
    )
    created_chunks = await repository.create_chunks(
        [
            {
                "document_id": first_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "threshold-parent-a",
                "content": "parent a",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": first_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "threshold-child-a",
                "content": "threshold document a",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "threshold-parent-b",
                "content": "parent b",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "threshold-child-b",
                "content": "threshold document b",
                "modality": "text",
                "token_count": 3,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    first_chunk = created_chunks[1]
    second_chunk = created_chunks[3]
    project = await integration_session.get(query_module.RagProject, seeded_project["project_id"])
    project.config = {
        "retrieval": {
            "hybrid": {
                "score_threshold": 0.5,
            }
        }
    }
    await integration_session.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question("threshold", seeded_project["project_id"])

    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_id"] == str(first_chunk.id)


@pytest.mark.asyncio
async def test_query_service_queries_multiple_collections_with_rrf_merge(
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

    captured_collections: list[str] = []

    class FakeVectorStore:
        def __init__(self, collection_name: str | None = None):
            self.collection_name = collection_name or "rag_chunks"

        async def search_chunks(self, **kwargs):
            captured_collections.append(self.collection_name)
            if self.collection_name == "crm_docs":
                return [{"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.9}]
            return [{"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.8}]

        async def search_sparse_chunks(self, **kwargs):
            if self.collection_name == "crm_docs":
                return [{"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 2.1}]
            return [{"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 2.2}]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    first_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://crm",
        status="indexed",
        title="CRM Collection Doc",
        content_hash="multi-col-1",
        metadata={"content_text": "crm content"},
    )
    second_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://support",
        status="indexed",
        title="Support Collection Doc",
        content_hash="multi-col-2",
        metadata={"content_text": "support content"},
    )
    created_chunks = await repository.create_chunks(
        [
            {
                "document_id": first_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "mparent-1",
                "content": "crm parent",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": first_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "mchild-1",
                "content": "crm content",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "mparent-2",
                "content": "support parent",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "mchild-2",
                "content": "support content",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    first_chunk = created_chunks[1]
    second_chunk = created_chunks[3]
    await repository.commit()

    service = QueryService(
        integration_session,
        vector_store=FakeVectorStore(),
        vector_store_factory=lambda collection_name: FakeVectorStore(collection_name),
    )
    result = await service.answer_question(
        "crm support",
        seeded_project["project_id"],
        collections=["crm_docs", "support_docs"],
        merge_strategy="rrf",
    )

    assert captured_collections == ["crm_docs", "support_docs"]
    assert [source["chunk_id"] for source in result["sources"]] == [str(first_chunk.id), str(second_chunk.id)]


@pytest.mark.asyncio
async def test_query_service_applies_negative_filters_to_final_sources(
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
        async def search_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.99},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.98},
            ]

        async def search_sparse_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 2.1},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 2.0},
            ]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    first_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://crm",
        status="indexed",
        title="Keep Me",
        content_hash="neg-1",
        metadata={"content_text": "keep content"},
    )
    second_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://support",
        status="indexed",
        title="Exclude Me",
        content_hash="neg-2",
        metadata={"content_text": "exclude content"},
    )
    created_chunks = await repository.create_chunks(
        [
            {
                "document_id": first_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "neg-parent-1",
                "content": "parent keep",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": first_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "neg-child-1",
                "content": "keep content",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "neg-parent-2",
                "content": "parent exclude",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "neg-child-2",
                "content": "exclude content",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    first_chunk = created_chunks[1]
    second_chunk = created_chunks[3]
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question(
        "filter",
        seeded_project["project_id"],
        exclude_sources=["inline://support"],
        exclude_documents=[str(second_document.id)],
    )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_id"] == str(first_chunk.id)


@pytest.mark.asyncio
async def test_query_service_applies_acl_filter_to_final_sources(
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

    captured: dict[str, object] = {}

    class FakeVectorStore:
        async def search_chunks(self, **kwargs):
            captured["acl"] = kwargs.get("acl")
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 0.99},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 0.98},
            ]

        async def search_sparse_chunks(self, **kwargs):
            return [
                {"document_id": str(first_document.id), "chunk_id": str(first_chunk.id), "score": 2.1},
                {"document_id": str(second_document.id), "chunk_id": str(second_chunk.id), "score": 2.0},
            ]

    monkeypatch.setattr(query_module, "embed_query_text", fake_embed_query_text, raising=False)

    repository = IngestionRepository(integration_session)
    first_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://crm",
        status="indexed",
        title="Allowed Doc",
        content_hash="acl-1",
        metadata={"content_text": "allowed"},
    )
    second_document = await repository.create_document(
        project_id=seeded_project["project_id"],
        tenant_id=seeded_project["tenant_id"],
        source_type="structured",
        source_ref="inline://support",
        status="indexed",
        title="Denied Doc",
        content_hash="acl-2",
        metadata={"content_text": "denied"},
    )
    created_chunks = await repository.create_chunks(
        [
            {
                "document_id": first_document.id,
                "chunk_index": 0,
                "parent_chunk_id": None,
                "content_hash": "acl-parent-1",
                "content": "parent allowed",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": first_document.id,
                "chunk_index": 1,
                "parent_chunk_id": "__PARENT_INDEX__:0",
                "content_hash": "acl-child-1",
                "content": "allowed",
                "modality": "text",
                "token_count": 1,
                "page_number": None,
                "bbox": None,
                "section_title": "A",
                "acl": ["tenant:42"],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 2,
                "parent_chunk_id": None,
                "content_hash": "acl-parent-2",
                "content": "parent denied",
                "modality": "text",
                "token_count": 2,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": [],
                "embed_model": None,
                "embed_version": None,
                "dimension": 0,
            },
            {
                "document_id": second_document.id,
                "chunk_index": 3,
                "parent_chunk_id": "__PARENT_INDEX__:2",
                "content_hash": "acl-child-2",
                "content": "denied",
                "modality": "text",
                "token_count": 1,
                "page_number": None,
                "bbox": None,
                "section_title": "B",
                "acl": ["tenant:99"],
                "embed_model": "gemini-embedding-2",
                "embed_version": "v1",
                "dimension": 768,
            },
        ]
    )
    first_chunk = created_chunks[1]
    second_chunk = created_chunks[3]
    await repository.commit()

    service = QueryService(integration_session, vector_store=FakeVectorStore())
    result = await service.answer_question(
        "acl",
        seeded_project["project_id"],
        acl=["tenant:42"],
    )

    assert captured["acl"] == ["tenant:42"]
    assert len(result["sources"]) == 1
    assert result["sources"][0]["chunk_id"] == str(first_chunk.id)


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
