from __future__ import annotations

import httpx

from app.config import get_settings


class QdrantClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def get(self, path: str):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
            return await client.get(path)

    async def put(self, path: str, json: dict):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
            return await client.put(path, json=json)


class CollectionsService:
    def __init__(self, client: QdrantClient | None = None):
        settings = get_settings()
        self.dimension = settings.embed_dimension
        self.client = client or QdrantClient(settings.qdrant_url)

    async def list_collections(self) -> dict[str, object]:
        response = await self.client.get("/collections")
        response.raise_for_status()
        payload = response.json()
        collections = payload.get("result", {}).get("collections", [])
        return {
            "items": [
                {"name": collection["name"], "dimension": self.dimension}
                for collection in collections
            ]
        }

    async def create_collection(self, name: str) -> dict[str, object]:
        response = await self.client.put(
            f"/collections/{name}",
            json={
                "vectors": {
                    "size": self.dimension,
                    "distance": "Cosine",
                },
                "sparse_vectors": {
                    "sparse": {},
                },
            },
        )
        response.raise_for_status()
        return {
            "name": name,
            "dimension": self.dimension,
            "status": "created",
        }
