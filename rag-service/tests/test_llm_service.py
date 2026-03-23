import pytest

from app.services import llm as llm_module
from app.services.circuit_breaker import CircuitOpenError


@pytest.mark.asyncio
async def test_generate_uses_formatter_model_by_default(monkeypatch):
    captured: dict[str, object] = {}

    class FakeSettings:
        formatter_model = "gemini-2.5-flash"
        gemini_api_key = "secret-key"
        formatter_output_char_limit = 2000

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "YanIt"}],
                        }
                    }
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

    monkeypatch.setattr(llm_module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await llm_module.generate("Sadece kaynaklara dayan.")

    assert result == "YanIt"
    assert "models/gemini-2.5-flash:generateContent" in str(captured["url"])
    assert captured["headers"]["x-goog-api-key"] == "secret-key"


@pytest.mark.asyncio
async def test_generate_trims_output_to_formatter_output_limit(monkeypatch):
    class FakeSettings:
        formatter_model = "gemini-2.5-flash"
        gemini_api_key = "secret-key"
        formatter_output_char_limit = 5

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "123456789"}],
                        }
                    }
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(llm_module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    result = await llm_module.generate("Prompt")

    assert result == "12345"


@pytest.mark.asyncio
async def test_generate_short_circuits_when_breaker_open(monkeypatch):
    called = {"client": False}

    class FakeSettings:
        formatter_model = "gemini-2.5-flash"
        gemini_api_key = "secret-key"
        formatter_output_char_limit = 2000

    class FakeBreaker:
        def before_call(self):
            raise CircuitOpenError("gemini_llm")

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

    monkeypatch.setattr(llm_module, "get_circuit_breaker", lambda service_name: FakeBreaker())
    monkeypatch.setattr(llm_module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())

    with pytest.raises(CircuitOpenError):
        await llm_module.generate("Prompt")

    assert called["client"] is False


@pytest.mark.asyncio
async def test_generate_updates_trace_metadata(monkeypatch):
    updates: list[dict[str, object]] = []

    class FakeSettings:
        formatter_model = "gemini-2.5-flash"
        gemini_api_key = "secret-key"
        formatter_output_char_limit = 2000

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "YanIt"}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr(llm_module, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        llm_module,
        "update_current_observation",
        lambda **kwargs: updates.append(kwargs),
        raising=False,
    )

    result = await llm_module.generate("Prompt")

    assert result == "YanIt"
    assert updates[0]["metadata"] == {"provider": "gemini", "model": "gemini-2.5-flash"}
