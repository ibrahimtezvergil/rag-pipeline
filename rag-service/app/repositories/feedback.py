from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import RagChunk, RagChunkFeedback, RagDocument, RagProject


class FeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project(self, project_id: uuid.UUID) -> RagProject | None:
        return await self.session.get(RagProject, project_id)

    async def get_project_chunks(
        self,
        *,
        project_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> list[RagChunk]:
        result = await self.session.scalars(
            select(RagChunk)
            .join(RagDocument, RagChunk.document_id == RagDocument.id)
            .where(
                RagChunk.id.in_(chunk_ids),
                RagDocument.project_id == project_id,
                RagChunk.is_archived.is_(False),
            )
        )
        return list(result)

    async def create_feedback_entries(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        chunks: list[RagChunk],
        rating: str,
        note: str | None,
        query_hash: str | None,
    ) -> list[RagChunkFeedback]:
        rows: list[RagChunkFeedback] = []
        for chunk in chunks:
            row = RagChunkFeedback(
                tenant_id=tenant_id,
                project_id=project_id,
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                rating=rating,
                note=note,
                query_hash=query_hash,
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def get_feedback_summary(
        self,
        *,
        project_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, dict[str, int]]:
        if not chunk_ids:
            return {}
        result = await self.session.scalars(
            select(RagChunkFeedback).where(
                RagChunkFeedback.project_id == project_id,
                RagChunkFeedback.chunk_id.in_(chunk_ids),
            )
        )
        counts: dict[uuid.UUID, Counter[str]] = {}
        for row in result:
            counter = counts.setdefault(row.chunk_id, Counter())
            counter[row.rating] += 1
        return {
            chunk_id: {"up": counter.get("up", 0), "down": counter.get("down", 0)}
            for chunk_id, counter in counts.items()
        }

    async def commit(self) -> None:
        await self.session.commit()
