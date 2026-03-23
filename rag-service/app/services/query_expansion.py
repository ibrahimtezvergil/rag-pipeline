from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.services.llm import generate as generate_text

_SYNONYMS = {
    "invoice": ["billing", "payment"],
    "renewal": ["extension", "contract renewal"],
    "customer": ["client", "account"],
}


@dataclass
class ExpandedQuery:
    original_question: str
    expanded_query: str
    synonyms_applied: list[str]
    rewrite_applied: bool


class QueryExpansionService:
    async def expand(self, question: str, *, use_llm: bool = False) -> ExpandedQuery:
        settings = get_settings()
        parts: list[str] = [question.strip()]
        synonyms_applied: list[str] = []

        for token in question.lower().split():
            for synonym in _SYNONYMS.get(token, []):
                if synonym not in synonyms_applied:
                    synonyms_applied.append(synonym)

        synonyms_applied = synonyms_applied[: settings.query_expansion_max_terms]
        parts.extend(synonyms_applied)
        synonym_query = " ".join(part for part in parts if part).strip() or question

        if use_llm:
            try:
                rewritten = (await generate_text(self._build_rewrite_prompt(question, synonym_query))).strip()
                if rewritten:
                    return ExpandedQuery(
                        original_question=question,
                        expanded_query=rewritten,
                        synonyms_applied=synonyms_applied,
                        rewrite_applied=True,
                    )
            except Exception:
                pass

        return ExpandedQuery(
            original_question=question,
            expanded_query=synonym_query,
            synonyms_applied=synonyms_applied,
            rewrite_applied=False,
        )

    def _build_rewrite_prompt(self, question: str, synonym_query: str) -> str:
        return (
            "Kullanicinin arama sorgusunu retrieval icin kisa ve aranabilir tek satir olarak yeniden yaz.\n"
            "Anlami koru, yeni iddia ekleme.\n"
            f"Orijinal: {question}\n"
            f"Synonym genisletilmis: {synonym_query}"
        )
