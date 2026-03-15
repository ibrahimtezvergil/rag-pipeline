from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_post_query_returns_answer(client, app, valid_headers):
    async def answer_question(
        question,
        project_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
    ):
        assert question == "Rapor ne anlatıyor?"
        assert str(project_id) == valid_headers["X-Project-ID"]
        assert scope_type is None
        assert scope_id is None
        assert entity_id is None
        assert snapshot_date is None
        assert tags is None
        return {
            "answer": "Rapor gelir artisini anlatiyor.",
            "retrieval_mode": "semantic_qdrant",
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
    assert response.json()["retrieval_context"] == [
        {
            "title": "report.pdf",
            "snippet": "Gelirler yillik bazda artti.",
            "parent_context": "",
            "score": 0.91,
        }
    ]
    assert len(response.json()["sources"]) == 1


@pytest.mark.asyncio
async def test_post_query_passes_scope_filters(client, app, valid_headers):
    async def answer_question(
        question,
        project_id,
        scope_type=None,
        scope_id=None,
        entity_id=None,
        snapshot_date=None,
        tags=None,
    ):
        assert question == "Musteri ozeti?"
        assert str(project_id) == valid_headers["X-Project-ID"]
        assert scope_type == "customer"
        assert scope_id == "cust_42"
        assert entity_id is None
        assert snapshot_date is None
        assert tags == ["crm"]
        return {
            "answer": "Filtrelenmis musteri ozeti.",
            "retrieval_mode": "metadata_fallback",
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
    assert response.json()["retrieval_mode"] == "metadata_fallback"
    assert response.json()["retrieval_context"] == []


@pytest.mark.asyncio
async def test_post_chat_returns_session_answer(client, app, valid_headers):
    async def reply(message, project_id, session_id=None):
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
