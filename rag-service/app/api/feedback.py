from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.feedback import FeedbackCreateRequest, FeedbackCreateResponse
from app.services.feedback import FeedbackService


router = APIRouter()


def _parse_application_id(raw_application_id: str) -> uuid.UUID:
    return uuid.UUID(raw_application_id)


def _get_feedback_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackService:
    service = getattr(request.app.state, "feedback_service", None)
    if service is not None:
        return service
    return FeedbackService(session)


@router.post("/feedback", response_model=FeedbackCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    request: Request,
    response: Response,
    payload: FeedbackCreateRequest,
    service: FeedbackService = Depends(_get_feedback_service),
):
    application_id = _parse_application_id(request.state.application_id)
    result = await service.create_feedback(payload, application_id)
    response.status_code = status.HTTP_201_CREATED
    return FeedbackCreateResponse.model_validate(result)
