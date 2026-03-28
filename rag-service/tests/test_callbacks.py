import json

import pytest

from app.services import callbacks as callbacks_module


def test_sign_ingestion_callback_is_deterministic(monkeypatch):
    class FakeSettings:
        ingest_callback_secret = "secret-123"

    monkeypatch.setattr(callbacks_module, "get_settings", lambda: FakeSettings(), raising=False)

    signature = callbacks_module.sign_ingestion_callback(b'{"a":1}')

    assert signature == callbacks_module.sign_ingestion_callback(b'{"a":1}')


@pytest.mark.asyncio
async def test_send_ingestion_callback_posts_signed_json(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSettings:
        ingest_callback_secret = "secret-123"

    class FakeResponse:
        status_code = 202

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, content, headers):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(callbacks_module, "get_settings", lambda: FakeSettings(), raising=False)
    monkeypatch.setattr(callbacks_module.httpx, "AsyncClient", lambda **kwargs: FakeClient(), raising=False)

    status_code = await callbacks_module.send_ingestion_callback(
        callback_url="https://example.com/callback",
        document_id="doc-1",
        ingestion_job_id="job-1",
        application_id="project-1",
        status="completed",
        source_type="web",
    )

    assert status_code == 202
    assert captured["url"] == "https://example.com/callback"
    assert json.loads(captured["content"])["status"] == "completed"
    assert captured["headers"]["X-RAG-Signature"]


@pytest.mark.asyncio
async def test_send_ingestion_callback_returns_none_on_failure(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, content, headers):
            raise RuntimeError("network down")

    monkeypatch.setattr(callbacks_module.httpx, "AsyncClient", lambda **kwargs: FakeClient(), raising=False)

    status_code = await callbacks_module.send_ingestion_callback(
        callback_url="https://example.com/callback",
        document_id="doc-1",
        ingestion_job_id="job-1",
        application_id="project-1",
        status="failed",
        source_type="web",
        error_message="boom",
    )

    assert status_code is None
