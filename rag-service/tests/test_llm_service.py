import pytest

from app.services import llm as llm_module


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
