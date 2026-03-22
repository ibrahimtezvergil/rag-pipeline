import pytest

from app.services.vector_store import QdrantVectorStore


class DummyResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_qdrant_vector_store_creates_fixed_dimension_collection(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return DummyResponse()

    monkeypatch.setattr("app.services.vector_store.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.services.vector_store.get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {"qdrant_url": "http://qdrant:6333", "qdrant_collection": "rag_chunks", "embed_dimension": 768},
        )(),
    )

    store = QdrantVectorStore()
    await store.ensure_collection()

    assert captured == {
        "path": "/collections/rag_chunks",
        "json": {
            "vectors": {"dense": {"size": 768, "distance": "Cosine"}},
            "sparse_vectors": {"sparse": {}},
        },
    }


@pytest.mark.asyncio
async def test_qdrant_vector_store_upserts_payload_and_deletes_points(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def put(self, path, json=None):
            captured["put_path"] = path
            captured["put_json"] = json
            return DummyResponse()

        async def post(self, path, json=None):
            captured["post_path"] = path
            captured["post_json"] = json
            return DummyResponse()

    monkeypatch.setattr("app.services.vector_store.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.services.vector_store.get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {"qdrant_url": "http://qdrant:6333", "qdrant_collection": "rag_chunks", "embed_dimension": 768},
        )(),
    )

    store = QdrantVectorStore()
    point_ids = await store.upsert_chunks(
        [
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "tenant_id": "tenant-1",
                "scope_type": "project",
                "scope_id": "project-1",
                "source_type": "web",
                "modality": "text",
                "page_number": None,
                "acl": ["public"],
                "content": "hello",
                "vector": [0.1, 0.2, 0.3],
                "sparse_vector": {"indices": [7, 11], "values": [2.0, 1.0]},
            }
        ]
    )
    await store.delete_points(point_ids)

    payload = captured["put_json"]["points"][0]["payload"]
    vector = captured["put_json"]["points"][0]["vector"]
    assert captured["put_path"] == "/collections/rag_chunks/points"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["scope_type"] == "project"
    assert payload["scope_id"] == "project-1"
    assert payload["source_type"] == "web"
    assert payload["modality"] == "text"
    assert payload["acl"] == ["public"]
    assert vector["dense"] == [0.1, 0.2, 0.3]
    assert vector["sparse"] == {"indices": [7, 11], "values": [2.0, 1.0]}
    assert captured["post_path"] == "/collections/rag_chunks/points/delete"
    assert captured["post_json"] == {"points": point_ids}


@pytest.mark.asyncio
async def test_qdrant_vector_store_scrolls_document_ids_with_payload_filter(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return DummyResponse(
                {
                    "result": {
                        "points": [
                            {"payload": {"document_id": "doc-1"}},
                            {"payload": {"document_id": "doc-2"}},
                            {"payload": {"document_id": "doc-1"}},
                        ]
                    }
                }
            )

    monkeypatch.setattr("app.services.vector_store.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.services.vector_store.get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {"qdrant_url": "http://qdrant:6333", "qdrant_collection": "rag_chunks", "embed_dimension": 768},
        )(),
    )

    store = QdrantVectorStore()
    document_ids = await store.filter_document_ids(
        tenant_id="tenant-1",
        scope_type="customer",
        scope_id="cust_42",
        entity_id="cust_42",
        snapshot_date="2026-03-15",
        tags=["crm", "daily-sync"],
    )

    assert document_ids == ["doc-1", "doc-2"]
    assert captured["path"] == "/collections/rag_chunks/points/scroll"
    assert captured["json"] == {
        "limit": 256,
        "with_payload": True,
        "with_vector": False,
        "filter": {
            "must": [
                {"key": "tenant_id", "match": {"value": "tenant-1"}},
                {"key": "scope_type", "match": {"value": "customer"}},
                {"key": "scope_id", "match": {"value": "cust_42"}},
                {"key": "entity_id", "match": {"value": "cust_42"}},
                {"key": "snapshot_date", "match": {"value": "2026-03-15"}},
                {"key": "tags", "match": {"value": "crm"}},
                {"key": "tags", "match": {"value": "daily-sync"}},
            ]
        },
    }


@pytest.mark.asyncio
async def test_qdrant_vector_store_queries_ranked_chunks_with_vector_and_filter(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return DummyResponse(
                {
                    "result": {
                        "points": [
                            {
                                "score": 0.93,
                                "payload": {
                                    "document_id": "doc-2",
                                    "chunk_id": "chunk-2",
                                },
                            },
                            {
                                "score": 0.81,
                                "payload": {
                                    "document_id": "doc-1",
                                    "chunk_id": "chunk-1",
                                },
                            },
                        ]
                    }
                }
            )

    monkeypatch.setattr("app.services.vector_store.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.services.vector_store.get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {"qdrant_url": "http://qdrant:6333", "qdrant_collection": "rag_chunks", "embed_dimension": 768},
        )(),
    )

    store = QdrantVectorStore()
    results = await store.search_chunks(
        query_vector=[0.1, 0.2, 0.3],
        tenant_id="tenant-1",
        scope_type="customer",
        scope_id="cust_42",
        entity_id="cust_42",
        snapshot_date="2026-03-15",
        tags=["crm"],
        acl=["tenant:42", "role:manager"],
        limit=5,
    )

    assert results == [
        {"document_id": "doc-2", "chunk_id": "chunk-2", "score": 0.93},
        {"document_id": "doc-1", "chunk_id": "chunk-1", "score": 0.81},
    ]
    assert captured["path"] == "/collections/rag_chunks/points/query"
    assert captured["json"] == {
        "limit": 5,
        "with_payload": True,
        "with_vector": False,
        "using": "dense",
        "query": [0.1, 0.2, 0.3],
        "filter": {
            "must": [
                {"key": "tenant_id", "match": {"value": "tenant-1"}},
                {"key": "scope_type", "match": {"value": "customer"}},
                {"key": "scope_id", "match": {"value": "cust_42"}},
                {"key": "entity_id", "match": {"value": "cust_42"}},
                {"key": "snapshot_date", "match": {"value": "2026-03-15"}},
                {"key": "tags", "match": {"value": "crm"}},
            ],
            "should": [
                {"key": "acl", "match": {"value": "tenant:42"}},
                {"key": "acl", "match": {"value": "role:manager"}},
            ],
        },
    }


@pytest.mark.asyncio
async def test_qdrant_vector_store_queries_sparse_ranked_chunks(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return DummyResponse(
                {
                    "result": {
                        "points": [
                            {
                                "score": 3.7,
                                "payload": {
                                    "document_id": "doc-7",
                                    "chunk_id": "chunk-7",
                                },
                            }
                        ]
                    }
                }
            )

    monkeypatch.setattr("app.services.vector_store.httpx.AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        "app.services.vector_store.get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {"qdrant_url": "http://qdrant:6333", "qdrant_collection": "rag_chunks", "embed_dimension": 768},
        )(),
    )

    store = QdrantVectorStore()
    results = await store.search_sparse_chunks(
        sparse_query={"indices": [1, 4, 9], "values": [1.0, 0.5, 2.0]},
        tenant_id="tenant-1",
        scope_type="customer",
        scope_id="cust_42",
        entity_id=None,
        snapshot_date=None,
        tags=["crm"],
        limit=4,
    )

    assert results == [{"document_id": "doc-7", "chunk_id": "chunk-7", "score": 3.7}]
    assert captured["path"] == "/collections/rag_chunks/points/query"
    assert captured["json"] == {
        "limit": 4,
        "with_payload": True,
        "with_vector": False,
        "using": "sparse",
        "query": {"indices": [1, 4, 9], "values": [1.0, 0.5, 2.0]},
        "filter": {
            "must": [
                {"key": "tenant_id", "match": {"value": "tenant-1"}},
                {"key": "scope_type", "match": {"value": "customer"}},
                {"key": "scope_id", "match": {"value": "cust_42"}},
                {"key": "tags", "match": {"value": "crm"}},
            ]
        },
    }
