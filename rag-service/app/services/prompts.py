from __future__ import annotations

from app.config import get_settings


def get_empty_query_answer() -> str:
    return "Bu proje icin sorgulanabilir indexed dokuman bulunamadi."


def build_query_answer_prompt(*, question: str, sources: list[dict[str, object]]) -> str:
    sections = [
        "Yalnizca verilen kaynaklara dayanarak cevap ver.",
        "Kaynakta olmayan bilgiyi uydurma.",
        f"Soru: {question}",
        "Kaynaklar:",
    ]
    for index, source in enumerate(sources, start=1):
        sections.append(
            (
                f"{index}. Baslik: {source.get('title', '')}\n"
                f"Kaynak: {source.get('source_ref', '')}\n"
                f"Snippet: {source.get('snippet', '')}\n"
                f"Baglam: {source.get('parent_context', '')}"
            )
        )

    prompt = "\n\n".join(sections)
    limit = get_settings().formatter_input_char_limit
    return prompt[:limit]
