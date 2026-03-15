from __future__ import annotations

import uuid

import httpx

from app.config import get_settings


class QdrantVectorStore:
    def __init__(self, base_url: str | None = None, collection_name: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.qdrant_url).rstrip("/")
        self.collection_name = collection_name or settings.qdrant_collection
        self.dimension = settings.embed_dimension

    async def ensure_collection(self) -> None:
        payload = {
            "vectors": {
                "size": self.dimension,
                "distance": "Cosine",
            }
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as client:
            response = await client.put(f"/collections/{self.collection_name}", json=payload)
            response.raise_for_status()

    async def upsert_chunks(self, chunks: list[dict[str, object]]) -> list[str]:
        points = []
        point_ids: list[str] = []
        for chunk in chunks:
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)
            points.append(
                {
                    "id": point_id,
                    "vector": chunk["vector"],
                    "payload": {
                        "document_id": chunk["document_id"],
                        "chunk_id": chunk["chunk_id"],
                        "tenant_id": chunk["tenant_id"],
                        "scope_type": chunk["scope_type"],
                        "scope_id": chunk["scope_id"],
                        "origin": chunk.get("origin"),
                        "entity_type": chunk.get("entity_type"),
                        "entity_id": chunk.get("entity_id"),
                        "record_ids": chunk.get("record_ids", []),
                        "snapshot_date": chunk.get("snapshot_date"),
                        "tags": chunk.get("tags", []),
                        "source_type": chunk["source_type"],
                        "modality": chunk["modality"],
                        "page_number": chunk.get("page_number"),
                        "acl": chunk.get("acl", []),
                    },
                }
            )

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.put(
                f"/collections/{self.collection_name}/points",
                json={"points": points},
            )
            response.raise_for_status()

        return point_ids

    async def filter_document_ids(
        self,
        *,
        tenant_id: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        entity_id: str | None = None,
        snapshot_date: str | None = None,
        tags: list[str] | None = None,
    ) -> list[str]:
        must_filters = [{"key": "tenant_id", "match": {"value": tenant_id}}]
        if scope_type is not None:
            must_filters.append({"key": "scope_type", "match": {"value": scope_type}})
        if scope_id is not None:
            must_filters.append({"key": "scope_id", "match": {"value": scope_id}})
        if entity_id is not None:
            must_filters.append({"key": "entity_id", "match": {"value": entity_id}})
        if snapshot_date is not None:
            must_filters.append({"key": "snapshot_date", "match": {"value": snapshot_date}})
        for tag in tags or []:
            must_filters.append({"key": "tags", "match": {"value": tag}})

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post(
                f"/collections/{self.collection_name}/points/scroll",
                json={
                    "limit": 256,
                    "with_payload": True,
                    "with_vector": False,
                    "filter": {"must": must_filters},
                },
            )
            response.raise_for_status()

        points = response.json().get("result", {}).get("points", [])
        document_ids: list[str] = []
        for point in points:
            document_id = point.get("payload", {}).get("document_id")
            if document_id and document_id not in document_ids:
                document_ids.append(document_id)
        return document_ids

    async def search_chunks(
        self,
        *,
        query_vector: list[float],
        tenant_id: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
        entity_id: str | None = None,
        snapshot_date: str | None = None,
        tags: list[str] | None = None,
        limit: int = 6,
    ) -> list[dict[str, object]]:
        must_filters = [{"key": "tenant_id", "match": {"value": tenant_id}}]
        if scope_type is not None:
            must_filters.append({"key": "scope_type", "match": {"value": scope_type}})
        if scope_id is not None:
            must_filters.append({"key": "scope_id", "match": {"value": scope_id}})
        if entity_id is not None:
            must_filters.append({"key": "entity_id", "match": {"value": entity_id}})
        if snapshot_date is not None:
            must_filters.append({"key": "snapshot_date", "match": {"value": snapshot_date}})
        for tag in tags or []:
            must_filters.append({"key": "tags", "match": {"value": tag}})

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post(
                f"/collections/{self.collection_name}/points/query",
                json={
                    "limit": limit,
                    "with_payload": True,
                    "with_vector": False,
                    "query": query_vector,
                    "filter": {"must": must_filters},
                },
            )
            response.raise_for_status()

        points = response.json().get("result", {}).get("points", [])
        return [
            {
                "document_id": point.get("payload", {}).get("document_id"),
                "chunk_id": point.get("payload", {}).get("chunk_id"),
                "score": point.get("score", 0.0),
            }
            for point in points
            if point.get("payload", {}).get("document_id")
        ]

    async def delete_points(self, point_ids: list[str]) -> None:
        if not point_ids:
            return

        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
            response = await client.post(
                f"/collections/{self.collection_name}/points/delete",
                json={"points": point_ids},
            )
            response.raise_for_status()
