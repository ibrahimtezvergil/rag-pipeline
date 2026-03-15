import pytest

from app.services import summary_formatter as summary_formatter_module
from app.services.summary_formatter import (
    _generate_semantic_summary,
    format_structured_data,
    format_structured_data_semantically,
)


def test_format_structured_dict_into_natural_language():
    result = format_structured_data(
        {
            "customer": "Acme",
            "plan": "growth",
            "active": True,
        },
        title="CRM Record",
    )

    assert "CRM Record" in result
    assert "customer is Acme" in result
    assert "plan is growth" in result
    assert "active is true" in result


def test_format_structured_table_rows_into_readable_sentences():
    result = format_structured_data(
        [
            {"name": "Ali", "score": 91},
            {"name": "Ayse", "score": 88},
        ],
        title="Leaderboard",
    )

    assert "Leaderboard" in result
    assert "Row 1" in result
    assert "name is Ali" in result
    assert "score is 88" in result


@pytest.mark.asyncio
async def test_format_structured_data_semantically_uses_llm_response(monkeypatch):
    async def fake_generate_semantic_summary(*, data, title):
        assert title == "CRM Customer Snapshot"
        assert data == [{"customer_id": 42, "company_name": "Acme Mobilya"}]
        return {
            "text": "Acme Mobilya isimli musteri aktif olarak izleniyor.",
            "model": "gemini-test",
            "mode": "llm_semantic",
        }

    monkeypatch.setattr(
        summary_formatter_module,
        "_generate_semantic_summary",
        fake_generate_semantic_summary,
        raising=False,
    )
    monkeypatch.setattr(
        summary_formatter_module,
        "get_settings",
        lambda: type("FakeSettings", (), {"gemini_api_key": "secret-key"})(),
    )

    result = await format_structured_data_semantically(
        [{"customer_id": 42, "company_name": "Acme Mobilya"}],
        title="CRM Customer Snapshot",
    )

    assert result == {
        "text": "Acme Mobilya isimli musteri aktif olarak izleniyor.",
        "model": "gemini-test",
        "mode": "llm_semantic",
    }


@pytest.mark.asyncio
async def test_generate_semantic_summary_sanitizes_prompt_payload(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {"content": {"parts": [{"text": "Semantic summary"}]}}
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

    monkeypatch.setattr(
        summary_formatter_module,
        "get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {
                "gemini_api_key": "secret-key",
                "formatter_model": "gemini-test",
                "formatter_output_char_limit": 400,
                "formatter_input_char_limit": 4000,
            },
        )(),
    )
    monkeypatch.setattr(
        summary_formatter_module.httpx,
        "AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    await _generate_semantic_summary(
        data=[
            {
                "customer_id": 42,
                "email": "user@example.com",
                "phone": "+90 555 123 45 67",
                "note": "",
                "nested": {"stage": "negotiation", "empty": None},
                "items": [],
            }
        ],
        title="CRM Customer Snapshot",
    )

    prompt = captured["json"]["contents"][0]["parts"][0]["text"]
    assert "user@example.com" not in prompt
    assert "+90 555 123 45 67" not in prompt
    assert "[redacted-email]" in prompt
    assert "[redacted-phone]" in prompt
    assert '"note": ""' not in prompt
    assert '"items": []' not in prompt
    assert '"empty": null' not in prompt


@pytest.mark.asyncio
async def test_format_structured_data_semantically_truncates_long_llm_output(monkeypatch):
    async def fake_generate_semantic_summary(*, data, title):
        return {
            "text": "A" * 120,
            "model": "gemini-test",
            "mode": "llm_semantic",
        }

    monkeypatch.setattr(
        summary_formatter_module,
        "_generate_semantic_summary",
        fake_generate_semantic_summary,
        raising=False,
    )
    monkeypatch.setattr(
        summary_formatter_module,
        "get_settings",
        lambda: type(
            "FakeSettings",
            (),
            {
                "gemini_api_key": "secret-key",
                "formatter_output_char_limit": 40,
            },
        )(),
    )

    result = await format_structured_data_semantically(
        [{"customer_id": 42}],
        title="CRM Customer Snapshot",
    )

    assert len(result["text"]) <= 40
    assert result["text"].endswith("...")
