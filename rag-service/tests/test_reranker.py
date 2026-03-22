import pytest

from app.services import reranker as reranker_module


@pytest.mark.asyncio
async def test_cohere_reranker_calls_v2_rerank_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.98},
                    {"index": 0, "relevance_score": 0.41},
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(reranker_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"cohere_api_key": "cohere-key"})(),
    )

    service = reranker_module.CohereRerankerService()
    results = await service.rerank(
        query="renewal billing",
        documents=["doc a", "doc b"],
        top_n=2,
    )

    assert captured["url"] == "https://api.cohere.com/v2/rerank"
    assert captured["headers"] == {
        "Authorization": "Bearer cohere-key",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {
        "model": "rerank-v3.5",
        "query": "renewal billing",
        "documents": ["doc a", "doc b"],
        "top_n": 2,
    }
    assert results == [
        {"index": 1, "score": 0.98},
        {"index": 0, "score": 0.41},
    ]
