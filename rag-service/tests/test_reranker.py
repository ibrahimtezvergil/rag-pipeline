import pytest

from app.services import reranker as reranker_module
from app.services.circuit_breaker import CircuitOpenError


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


@pytest.mark.asyncio
async def test_reranker_short_circuits_when_breaker_open(monkeypatch):
    called = {"client": False}

    class FakeBreaker:
        def before_call(self):
            raise CircuitOpenError("cohere_rerank")

        def record_success(self):
            return None

        def record_failure(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            called["client"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(reranker_module, "get_circuit_breaker", lambda service_name: FakeBreaker())
    monkeypatch.setattr(reranker_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"cohere_api_key": "cohere-key"})(),
    )

    with pytest.raises(CircuitOpenError):
        await reranker_module.CohereRerankerService().rerank(
            query="renewal billing",
            documents=["doc a"],
            top_n=1,
        )

    assert called["client"] is False


@pytest.mark.asyncio
async def test_reranker_updates_trace_metadata(monkeypatch):
    updates: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"index": 0, "relevance_score": 0.5}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(reranker_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        reranker_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"cohere_api_key": "cohere-key"})(),
    )
    monkeypatch.setattr(
        reranker_module,
        "update_current_observation",
        lambda **kwargs: updates.append(kwargs),
        raising=False,
    )

    await reranker_module.CohereRerankerService().rerank(
        query="renewal billing",
        documents=["doc a"],
        top_n=1,
    )

    assert updates[0]["metadata"] == {
        "provider": "cohere",
        "model": "rerank-v3.5",
        "top_n": 1,
    }
