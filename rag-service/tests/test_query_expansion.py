import pytest

from app.services.query_expansion import QueryExpansionService


@pytest.mark.asyncio
async def test_query_expansion_adds_synonyms():
    service = QueryExpansionService()

    result = await service.expand("invoice renewal")

    assert result.original_question == "invoice renewal"
    assert "billing" in result.expanded_query
    assert "payment" in result.expanded_query
    assert "contract renewal" in result.expanded_query
    assert result.rewrite_applied is False


@pytest.mark.asyncio
async def test_query_expansion_uses_llm_rewrite_when_enabled(monkeypatch):
    service = QueryExpansionService()

    async def fake_generate(prompt: str) -> str:
        return "invoice billing history"

    monkeypatch.setattr("app.services.query_expansion.generate_text", fake_generate)

    result = await service.expand("invoice", use_llm=True)

    assert result.expanded_query == "invoice billing history"
    assert result.rewrite_applied is True


@pytest.mark.asyncio
async def test_query_expansion_falls_back_to_synonyms_when_llm_fails(monkeypatch):
    service = QueryExpansionService()

    async def fake_generate(prompt: str) -> str:
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("app.services.query_expansion.generate_text", fake_generate)

    result = await service.expand("invoice", use_llm=True)

    assert "billing" in result.expanded_query
    assert result.rewrite_applied is False
