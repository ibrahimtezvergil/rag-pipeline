import pytest

from app.services import prompts as prompts_module


def test_build_query_answer_prompt_includes_question_sources_and_context(monkeypatch):
    class FakeSettings:
        formatter_input_char_limit = 500

    monkeypatch.setattr(prompts_module, "get_settings", lambda: FakeSettings())

    prompt = prompts_module.build_query_answer_prompt(
        question="Q1 gelir artisi neden oldu?",
        sources=[
            {
                "title": "Q1 Report",
                "source_ref": "https://example.com/q1",
                "snippet": "Subscription satislari gelir artisina onculuk etti.",
                "parent_context": "Gelir ozeti ve kanal bazli dagilim.",
            }
        ],
    )

    assert "Q1 gelir artisi neden oldu?" in prompt
    assert "Q1 Report" in prompt
    assert "https://example.com/q1" in prompt
    assert "Subscription satislari gelir artisina onculuk etti." in prompt
    assert "Gelir ozeti ve kanal bazli dagilim." in prompt


def test_build_query_answer_prompt_trims_to_formatter_input_budget(monkeypatch):
    class FakeSettings:
        formatter_input_char_limit = 160

    monkeypatch.setattr(prompts_module, "get_settings", lambda: FakeSettings())

    prompt = prompts_module.build_query_answer_prompt(
        question="Kisa soru",
        sources=[
            {
                "title": "Long Source",
                "source_ref": "https://example.com/long",
                "snippet": "A" * 400,
                "parent_context": "B" * 400,
            }
        ],
    )

    assert len(prompt) <= 160
    assert "Kisa soru" in prompt


def test_get_empty_query_answer_returns_safe_message():
    assert prompts_module.get_empty_query_answer() == "Bu proje icin sorgulanabilir indexed dokuman bulunamadi."
