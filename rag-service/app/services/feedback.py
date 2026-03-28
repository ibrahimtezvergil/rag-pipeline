from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import FeedbackCreateRequest


class FeedbackService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        repository: FeedbackRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or FeedbackRepository(session)

    async def create_feedback(
        self,
        payload: FeedbackCreateRequest,
        project_id: uuid.UUID,
    ) -> dict[str, object]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        unique_chunk_ids = list(dict.fromkeys(payload.chunk_ids))
        chunks = await self.repository.get_project_chunks(
            project_id=project_id,
            chunk_ids=unique_chunk_ids,
        )
        if len(chunks) != len(unique_chunk_ids):
            raise HTTPException(status_code=400, detail="One or more chunk_ids are invalid for this project")

        await self.repository.create_feedback_entries(
            tenant_id=project.tenant_id,
            project_id=project.id,
            chunks=chunks,
            rating=payload.rating,
            note=payload.note,
            query_hash=payload.query_hash,
        )
        await self.repository.commit()
        return {
            "status": "recorded",
            "rating": payload.rating,
            "recorded_count": len(chunks),
        }
