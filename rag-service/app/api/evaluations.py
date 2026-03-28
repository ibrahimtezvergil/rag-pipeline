from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.evaluations import EvaluationCreateRequest, EvaluationRunResponse
from app.services.evaluations import EvaluationService


router = APIRouter()


def _parse_application_id(raw_application_id: str) -> uuid.UUID:
    return uuid.UUID(raw_application_id)


def _get_evaluation_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> EvaluationService:
    service = getattr(request.app.state, "evaluation_service", None)
    if service is not None:
        return service
    dispatcher = getattr(request.app.state, "evaluation_dispatcher", None)
    return EvaluationService(session, dispatcher=dispatcher)


@router.post("/evaluations", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    request: Request,
    response: Response,
    payload: EvaluationCreateRequest,
    service: EvaluationService = Depends(_get_evaluation_service),
):
    application_id = _parse_application_id(request.state.application_id)
    result = await service.create_run(payload, application_id)
    response.status_code = status.HTTP_201_CREATED
    return EvaluationRunResponse.model_validate(result)


@router.get("/evaluations/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation(
    request: Request,
    run_id: str,
    service: EvaluationService = Depends(_get_evaluation_service),
):
    application_id = _parse_application_id(request.state.application_id)
    result = await service.get_run(run_id, application_id)
    return EvaluationRunResponse.model_validate(result)
