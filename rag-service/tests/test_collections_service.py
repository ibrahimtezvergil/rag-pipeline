import pytest
import httpx

from app.services.collections import CollectionsService


class DummyResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "http://testserver"),
                response=httpx.Response(self.status_code),
            )


class FakeQdrantClient:
    async def get(self, path):
        assert path == "/collections"
        return DummyResponse(
            {
                "result": {
                    "collections": [
                        {"name": "rag_chunks"},
                        {"name": "crm_docs"},
                    ]
                }
            }
        )

    async def put(self, path, json):
        assert path == "/collections/crm_docs"
        assert json["vectors"]["size"] == 768
        return DummyResponse({"result": True}, status_code=200)


@pytest.mark.asyncio
async def test_collections_service_lists_collections():
    service = CollectionsService(client=FakeQdrantClient())

    result = await service.list_collections()

    assert result == {
        "items": [
            {"name": "rag_chunks", "dimension": 768},
            {"name": "crm_docs", "dimension": 768},
        ]
    }


@pytest.mark.asyncio
async def test_collections_service_creates_collection():
    service = CollectionsService(client=FakeQdrantClient())

    result = await service.create_collection("crm_docs")

    assert result == {
        "name": "crm_docs",
        "dimension": 768,
        "status": "created",
    }
