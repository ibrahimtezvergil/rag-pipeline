from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.circuit_breaker import get_circuit_breaker
from app.services.tracing import observe, update_current_observation


class CohereRerankerService:
    def __init__(self, *, model: str = "rerank-v3.5") -> None:
        self.model = model

    @observe(name="cohere-rerank", as_type="retriever")
    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[dict[str, float | int]]:
        settings = get_settings()
        update_current_observation(
            metadata={
                "provider": "cohere",
                "model": self.model,
                "top_n": top_n,
            }
        )
        breaker = get_circuit_breaker("cohere_rerank")
        breaker.before_call()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.cohere.com/v2/rerank",
                    headers={
                        "Authorization": f"Bearer {settings.cohere_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "query": query,
                        "documents": documents,
                        "top_n": top_n,
                    },
                )
                response.raise_for_status()
            except Exception:
                breaker.record_failure()
                raise
        breaker.record_success()

        return [
            {
                "index": int(item["index"]),
                "score": float(item["relevance_score"]),
            }
            for item in response.json().get("results", [])
        ]
