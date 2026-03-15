import pytest
import httpx

from app.services import embedder as embedder_module


@pytest.mark.asyncio
async def test_gemini_embedder_calls_embed_content_endpoint(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "embedding": {
                    "values": [0.1, 0.2, 0.3],
                }
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

    monkeypatch.setattr(embedder_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        embedder_module,
        "get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {
                "gemini_api_key": "secret-key",
                "embed_model": "gemini-embedding-001",
                "embed_dimension": 768,
            },
        )(),
    )

    result = await embedder_module.embed_pdf_document(
        content="PDF body text",
        title="report.pdf",
    )

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-embedding-001:embedContent"
    )
    assert captured["headers"] == {
        "x-goog-api-key": "secret-key",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": "PDF body text"}]},
        "taskType": "RETRIEVAL_DOCUMENT",
        "title": "report.pdf",
        "outputDimensionality": 768,
    }
    assert result == {
        "provider": "gemini",
        "model": "gemini-embedding-001",
        "task_type": "RETRIEVAL_DOCUMENT",
        "embed_version": "gemini-embedding-001-768",
        "status": "completed",
        "values": [0.1, 0.2, 0.3],
        "dimension": 3,
        "vector_dimension": 3,
    }


@pytest.mark.asyncio
async def test_query_embedder_uses_retrieval_query_task_type(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"embedding": {"values": [0.1, 0.2]}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(embedder_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(
        embedder_module,
        "get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {
                "gemini_api_key": "secret-key",
                "embed_model": "gemini-embedding-001",
                "embed_dimension": 768,
            },
        )(),
    )

    result = await embedder_module.embed_query_text("search term")

    assert captured["json"]["taskType"] == "RETRIEVAL_QUERY"
    assert result["task_type"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_embedder_retries_rate_limit_with_exponential_backoff(monkeypatch):
    calls = {"count": 0}
    sleeps: list[int] = []

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "rate limited",
                    request=httpx.Request("POST", "http://test"),
                    response=httpx.Response(self.status_code),
                )
            return None

        def json(self):
            return {"embedding": {"values": [0.1, 0.2, 0.3]}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            calls["count"] += 1
            if calls["count"] < 3:
                return FakeResponse(429)
            return FakeResponse(200)

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(embedder_module.httpx, "AsyncClient", lambda timeout=30.0: FakeClient())
    monkeypatch.setattr(embedder_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        embedder_module,
        "get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {
                "gemini_api_key": "secret-key",
                "embed_model": "gemini-embedding-001",
                "embed_dimension": 768,
            },
        )(),
    )

    result = await embedder_module.embed_text_content("hello", "doc", task_type="RETRIEVAL_DOCUMENT")

    assert calls["count"] == 3
    assert sleeps == [1, 2]
    assert result["vector_dimension"] == 3


@pytest.mark.asyncio
async def test_prepare_pdf_embedding_returns_prepared_when_content_missing():
    result = await embedder_module.prepare_pdf_embedding(
        source_ref="https://example.com/files/report.pdf",
        metadata={"page_count": 3},
    )

    assert result["status"] == "prepared"
    assert result["source_ref"] == "https://example.com/files/report.pdf"
