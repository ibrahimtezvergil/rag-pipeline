from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api import ingest as ingest_api_module
from app.api import query as query_api_module


@pytest.mark.asyncio
async def test_post_evaluations_creates_run(client, app, valid_headers):
    async def create_run(payload, application_id):
        assert payload.dataset_name == "smoke-set"
        assert len(payload.samples) == 1
        assert payload.samples[0].question == "Which invoice was paid?"
        assert str(application_id) == valid_headers["X-Application-ID"]
        return {
            "run_id": str(uuid4()),
            "status": "pending",
            "dataset_name": "smoke-set",
            "sample_count": 1,
        }

    app.state.evaluation_service = SimpleNamespace(create_run=create_run)

    response = await client.post(
        "/evaluations",
        headers=valid_headers,
        json={
            "dataset_name": "smoke-set",
            "samples": [
                {
                    "question": "Which invoice was paid?",
                    "ground_truth": "INV-1001 was paid.",
                    "reference_context": "Invoice INV-1001 status is paid.",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["dataset_name"] == "smoke-set"
    assert response.json()["sample_count"] == 1


@pytest.mark.asyncio
async def test_get_evaluation_returns_run_status(client, app, valid_headers):
    run_id = str(uuid4())

    async def get_run(run_id_arg, application_id):
        assert run_id_arg == run_id
        assert str(application_id) == valid_headers["X-Application-ID"]
        return {
            "run_id": run_id,
            "status": "completed",
            "dataset_name": "smoke-set",
            "sample_count": 2,
            "completed_count": 2,
            "faithfulness_avg": 0.8,
            "answer_relevancy_avg": 0.85,
            "context_recall_avg": 0.75,
        }

    app.state.evaluation_service = SimpleNamespace(get_run=get_run)

    response = await client.get(
        f"/evaluations/{run_id}",
        headers=valid_headers,
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == run_id
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_post_feedback_records_chunk_feedback(client, app, valid_headers):
    chunk_id = str(uuid4())

    async def create_feedback(payload, application_id):
        assert payload.rating == "down"
        assert [str(item) for item in payload.chunk_ids] == [chunk_id]
        assert payload.note == "Yanlis kaynak"
        assert str(application_id) == valid_headers["X-Application-ID"]
        return {
            "status": "recorded",
            "rating": "down",
            "recorded_count": 1,
        }

    app.state.feedback_service = SimpleNamespace(create_feedback=create_feedback)

    response = await client.post(
        "/feedback",
        headers=valid_headers,
        json={
            "rating": "down",
            "chunk_ids": [chunk_id],
            "note": "Yanlis kaynak",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "status": "recorded",
        "rating": "down",
        "recorded_count": 1,
    }


@pytest.mark.asyncio
async def test_post_schedules_creates_schedule(client, app, valid_headers):
    async def create_schedule(payload, application_id):
        assert payload.cron_expr == "*/30 * * * *"
        assert payload.ingest.source_type == "web"
        assert str(payload.ingest.source_ref) == "https://example.com/article"
        assert str(application_id) == valid_headers["X-Application-ID"]
        return {
            "schedule_id": str(uuid4()),
            "status": "enabled",
            "cron_expr": "*/30 * * * *",
            "next_run_at": "2026-03-23T10:30:00+00:00",
            "source_type": "web",
            "source_ref": "https://example.com/article",
        }

    app.state.schedule_service = SimpleNamespace(create_schedule=create_schedule)

    response = await client.post(
        "/schedules",
        headers=valid_headers,
        json={
            "cron_expr": "*/30 * * * *",
            "ingest": {
                "source_type": "web",
                "source_ref": "https://example.com/article",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "enabled"
    assert response.json()["cron_expr"] == "*/30 * * * *"


@pytest.mark.asyncio
async def test_post_query_returns_answer(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert question == "Rapor ne anlatıyor?"
        assert str(application_id) == valid_headers["X-Application-ID"]
        assert scope_type is None
        assert scope_id is None
        assert entity_id is None
        assert snapshot_date is None
        assert tags is None
        assert acl is None
        assert retrieval_mode == "hybrid"
        assert collections is None
        assert merge_strategy == "rrf"
        assert exclude_sources is None
        assert exclude_documents is None
        return {
            "answer": "Rapor gelir artisini anlatiyor.",
            "retrieval_mode": "semantic_qdrant",
            "confidence_score": 0.91,
            "confidence_warning": None,
            "retrieval_context": [
                {
                    "title": "report.pdf",
                    "snippet": "Gelirler yillik bazda artti.",
                    "parent_context": "",
                    "score": 0.91,
                }
            ],
            "sources": [
                {
                    "document_id": str(uuid4()),
                    "title": "report.pdf",
                    "source_ref": "https://example.com/report.pdf",
                    "snippet": "Gelirler yillik bazda artti.",
                    "score": 0.91,
                }
            ],
            "query_embedding": {
                "values": [0.1, 0.2],
                "dimension": 2,
            },
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={"question": "Rapor ne anlatıyor?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Rapor gelir artisini anlatiyor."
    assert response.json()["retrieval_mode"] == "semantic_qdrant"
    assert response.json()["confidence_score"] == 0.91
    assert response.json()["confidence_warning"] is None
    assert response.json()["retrieval_context"] == [
        {
            "title": "report.pdf",
            "snippet": "Gelirler yillik bazda artti.",
            "parent_context": "",
            "score": 0.91,
        }
    ]
    assert "query_embedding" not in response.json()
    assert len(response.json()["sources"]) == 1


@pytest.mark.asyncio
async def test_post_query_response_includes_confidence_fields(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        return {
            "answer": "Kisa cevap.",
            "retrieval_mode": "hybrid_rrf",
            "confidence_score": 0.42,
            "confidence_warning": None,
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={"question": "Durum nedir?"},
    )

    assert response.status_code == 200
    assert response.json()["confidence_score"] == 0.42
    assert response.json()["confidence_warning"] is None


@pytest.mark.asyncio
async def test_post_query_returns_429_when_rate_limited(client, app, valid_headers):
    async def check(*, application_id, route_name, limit):
        assert application_id == valid_headers["X-Application-ID"]
        assert route_name == "query"
        assert limit == 60
        return SimpleNamespace(allowed=False, retry_after_seconds=17)

    app.state.rate_limiter = SimpleNamespace(check=check)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={"question": "Rapor ne anlatıyor?"},
    )

    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert response.headers["Retry-After"] == "17"


@pytest.mark.asyncio
async def test_post_query_passes_scope_filters(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert question == "Musteri ozeti?"
        assert str(application_id) == valid_headers["X-Application-ID"]
        assert scope_type == "customer"
        assert scope_id == "cust_42"
        assert entity_id is None
        assert snapshot_date is None
        assert tags == ["crm"]
        assert acl is None
        assert retrieval_mode == "hybrid"
        assert collections is None
        assert merge_strategy == "rrf"
        assert exclude_sources is None
        assert exclude_documents is None
        return {
            "answer": "Filtrelenmis musteri ozeti.",
            "retrieval_mode": "hybrid_rrf",
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={
            "question": "Musteri ozeti?",
            "scope_type": "customer",
            "scope_id": "cust_42",
            "tags": ["crm"],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Filtrelenmis musteri ozeti."
    assert response.json()["retrieval_mode"] == "hybrid_rrf"
    assert response.json()["retrieval_context"] == []


@pytest.mark.asyncio
async def test_post_query_passes_sparse_retrieval_mode(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert question == "Anahtar kelime ara"
        assert acl is None
        assert retrieval_mode == "sparse"
        assert collections is None
        assert merge_strategy == "rrf"
        assert exclude_sources is None
        assert exclude_documents is None
        return {
            "answer": "Sparse sonuc hazir.",
            "retrieval_mode": "sparse_qdrant",
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={"question": "Anahtar kelime ara", "retrieval_mode": "sparse"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Sparse sonuc hazir."
    assert response.json()["retrieval_mode"] == "sparse_qdrant"


@pytest.mark.asyncio
async def test_post_query_passes_multi_collection_request(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert retrieval_mode == "hybrid"
        assert acl is None
        assert collections == ["crm_docs", "support_docs"]
        assert merge_strategy == "rrf"
        assert exclude_sources is None
        assert exclude_documents is None
        return {
            "answer": "Coklu collection sonucu.",
            "retrieval_mode": "hybrid_rrf",
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={
            "question": "Musteri gecmisi",
            "collections": ["crm_docs", "support_docs"],
            "merge_strategy": "rrf",
        },
    )

    assert response.status_code == 200
    assert response.json()["retrieval_mode"] == "hybrid_rrf"


@pytest.mark.asyncio
async def test_post_query_passes_negative_filters(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert acl is None
        assert exclude_sources == ["inline://crm", "inline://support"]
        assert exclude_documents == ["doc-1", "doc-2"]
        return {
            "answer": "Filtered",
            "retrieval_mode": "hybrid_rrf",
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={
            "question": "hariç tut",
            "exclude_sources": ["inline://crm", "inline://support"],
            "exclude_documents": ["doc-1", "doc-2"],
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_query_passes_acl_filters(client, app, valid_headers):
    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        assert acl == ["tenant:42", "role:manager"]
        return {
            "answer": "ACL filtered",
            "retrieval_mode": "hybrid_rrf",
            "retrieval_context": [],
            "sources": [],
        }

    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={
            "question": "izinli dokumanlar",
            "acl": ["tenant:42", "role:manager"],
        },
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_chat_returns_session_answer(client, app, valid_headers):
    async def reply(message, application_id, session_id=None):
        assert message == "Bu raporun ozeti ne?"
        assert session_id is None
        return {
            "session_id": "session-123",
            "answer": "Raporun ozeti hazir.",
            "retrieval_mode": "semantic_qdrant",
            "retrieval_context": [
                {
                    "title": "report.pdf",
                    "snippet": "Gelirler yillik bazda artti.",
                    "parent_context": "",
                }
            ],
            "sources": [],
        }

    app.state.chat_service = SimpleNamespace(reply=reply)

    response = await client.post(
        "/chat",
        headers=valid_headers,
        json={"message": "Bu raporun ozeti ne?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "session-123",
        "answer": "Raporun ozeti hazir.",
        "retrieval_mode": "semantic_qdrant",
        "confidence_score": None,
        "confidence_warning": None,
        "retrieval_context": [
            {
                "title": "report.pdf",
                "snippet": "Gelirler yillik bazda artti.",
                "parent_context": "",
                "score": None,
            }
        ],
        "sources": [],
    }


@pytest.mark.asyncio
async def test_post_chat_returns_429_when_rate_limited(client, app, valid_headers):
    async def check(*, application_id, route_name, limit):
        assert route_name == "chat"
        assert limit == 60
        return SimpleNamespace(allowed=False, retry_after_seconds=9)

    app.state.rate_limiter = SimpleNamespace(check=check)

    response = await client.post(
        "/chat",
        headers=valid_headers,
        json={"message": "Bu raporun ozeti ne?"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "9"


@pytest.mark.asyncio
async def test_get_collections_lists_available_collections(client, app, valid_headers):
    async def list_collections():
        return {
            "items": [
                {"name": "rag_chunks", "dimension": 768},
                {"name": "crm_docs", "dimension": 768},
            ]
        }

    app.state.collections_service = SimpleNamespace(list_collections=list_collections)

    response = await client.get("/collections", headers=valid_headers)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"name": "rag_chunks", "dimension": 768},
            {"name": "crm_docs", "dimension": 768},
        ]
    }


@pytest.mark.asyncio
async def test_post_collections_creates_collection(client, app, valid_headers):
    async def create_collection(name):
        assert name == "crm_docs"
        return {"name": "crm_docs", "dimension": 768, "status": "created"}

    app.state.collections_service = SimpleNamespace(create_collection=create_collection)

    response = await client.post(
        "/collections",
        headers=valid_headers,
        json={"name": "crm_docs"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "name": "crm_docs",
        "dimension": 768,
        "status": "created",
    }


@pytest.mark.asyncio
async def test_post_ingest_returns_429_when_rate_limited(client, app, valid_headers):
    async def check(*, application_id, route_name, limit):
        assert route_name == "ingest"
        assert limit == 20
        return SimpleNamespace(allowed=False, retry_after_seconds=12)

    app.state.rate_limiter = SimpleNamespace(check=check)

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={"source_type": "web", "source_ref": "https://example.com/article", "mode": "async"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "12"


@pytest.mark.asyncio
async def test_post_ingest_batch_returns_429_when_rate_limited(client, app, valid_headers):
    async def check(*, application_id, route_name, limit):
        assert route_name == "ingest_batch"
        assert limit == 10
        return SimpleNamespace(allowed=False, retry_after_seconds=22)

    app.state.rate_limiter = SimpleNamespace(check=check)

    response = await client.post(
        "/ingest/batch",
        headers=valid_headers,
        json={
            "items": [
                {"source_type": "web", "source_ref": "https://example.com/article", "mode": "async"}
            ]
        },
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "22"


@pytest.mark.asyncio
async def test_get_collections_is_not_rate_limited(client, app, valid_headers):
    async def create_collection(name):
        raise AssertionError("should not be called")

    async def list_collections():
        return {"items": [{"name": "rag_chunks", "dimension": 768}]}

    async def check(*, application_id, route_name, limit):
        raise AssertionError("rate limiter should not run for collections")

    app.state.collections_service = SimpleNamespace(
        create_collection=create_collection,
        list_collections=list_collections,
    )
    app.state.rate_limiter = SimpleNamespace(check=check)

    response = await client.get("/collections", headers=valid_headers)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_query_updates_trace_metadata_without_raw_question(client, app, valid_headers, monkeypatch):
    captured: list[dict[str, object]] = []

    async def answer_question(
        question,
        application_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
        acl=None,
        retrieval_mode="dense",
        collections=None,
        merge_strategy="rrf",
        exclude_sources=None,
        exclude_documents=None,
    ):
        return {
            "answer": "Kisa cevap.",
            "retrieval_mode": "hybrid_rrf",
            "retrieval_context": [],
            "sources": [],
        }

    monkeypatch.setattr(
        query_api_module,
        "update_current_observation",
        lambda **kwargs: captured.append(kwargs),
        raising=False,
    )
    app.state.query_service = SimpleNamespace(answer_question=answer_question)

    response = await client.post(
        "/query",
        headers=valid_headers,
        json={"question": "Ham soru burada kalmali"},
    )

    assert response.status_code == 200
    assert captured
    assert captured[0]["metadata"]["application_id"] == valid_headers["X-Application-ID"]
    assert "question" not in captured[0]["metadata"]


@pytest.mark.asyncio
async def test_post_ingest_updates_trace_metadata_without_payload_body(client, app, valid_headers, monkeypatch):
    captured: list[dict[str, object]] = []

    async def create_ingestion_job(payload, application_id):
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "pending",
            "mode": "async",
            "source_type": payload.source_type,
        }

    monkeypatch.setattr(
        ingest_api_module,
        "update_current_observation",
        lambda **kwargs: captured.append(kwargs),
        raising=False,
    )
    app.state.ingestion_service = SimpleNamespace(create_ingestion_job=create_ingestion_job)

    response = await client.post(
        "/ingest?mode=async",
        headers=valid_headers,
        json={"source_type": "web", "source_ref": "https://example.com/article", "mode": "sync"},
    )

    assert response.status_code == 202
    assert captured
    assert captured[0]["metadata"]["application_id"] == valid_headers["X-Application-ID"]
    assert captured[0]["metadata"]["source_type"] == "web"
    assert "source_ref" not in captured[0]["metadata"]
