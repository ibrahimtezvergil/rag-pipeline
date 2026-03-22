from __future__ import annotations

import httpx

from app.config import get_settings


class CohereRerankerService:
    def __init__(self, *, model: str = "rerank-v3.5") -> None:
        self.model = model

    async def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int,
    ) -> list[dict[str, float | int]]:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
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

        return [
            {
                "index": int(item["index"]),
                "score": float(item["relevance_score"]),
            }
            for item in response.json().get("results", [])
        ]
