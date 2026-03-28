from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.feedback import FeedbackCreateRequest
from app.services.feedback import FeedbackService


@pytest.mark.asyncio
async def test_feedback_service_records_feedback_for_project_chunks():
    project_id = uuid4()
    tenant_id = uuid4()
    chunk_id = uuid4()
    document_id = uuid4()

    class FakeRepo:
        def __init__(self):
            self.created = None
            self.committed = False

        async def get_project(self, value):
            assert value == project_id
            return SimpleNamespace(id=project_id, tenant_id=tenant_id)

        async def get_project_chunks(self, *, project_id, chunk_ids):
            assert chunk_ids == [chunk_id]
            return [SimpleNamespace(id=chunk_id, document_id=document_id)]

        async def create_feedback_entries(self, **kwargs):
            self.created = kwargs
            return [object()]

        async def commit(self):
            self.committed = True

    repo = FakeRepo()
    service = FeedbackService(session=None, repository=repo)

    result = await service.create_feedback(
        FeedbackCreateRequest(rating="down", chunk_ids=[chunk_id], note="bad", query_hash="abc"),
        project_id,
    )

    assert result == {"status": "recorded", "rating": "down", "recorded_count": 1}
    assert repo.created["rating"] == "down"
    assert repo.committed is True


@pytest.mark.asyncio
async def test_feedback_service_rejects_unknown_chunk_ids():
    project_id = uuid4()
    tenant_id = uuid4()
    chunk_id = uuid4()

    class FakeRepo:
        async def get_project(self, value):
            return SimpleNamespace(id=project_id, tenant_id=tenant_id)

        async def get_project_chunks(self, *, project_id, chunk_ids):
            return []

    service = FeedbackService(session=None, repository=FakeRepo())

    with pytest.raises(HTTPException) as exc_info:
        await service.create_feedback(
            FeedbackCreateRequest(rating="down", chunk_ids=[chunk_id]),
            project_id,
        )

    assert exc_info.value.status_code == 400
