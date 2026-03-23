from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.schedules import ScheduleCreateRequest, ScheduleResponse
from app.services.schedules import ScheduleService


router = APIRouter()


def _parse_project_id(raw_project_id: str) -> uuid.UUID:
    return uuid.UUID(raw_project_id)


def _get_schedule_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ScheduleService:
    service = getattr(request.app.state, "schedule_service", None)
    if service is not None:
        return service
    return ScheduleService(session)


@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    request: Request,
    response: Response,
    payload: ScheduleCreateRequest,
    service: ScheduleService = Depends(_get_schedule_service),
):
    project_id = _parse_project_id(request.state.project_id)
    result = await service.create_schedule(payload, project_id)
    response.status_code = status.HTTP_201_CREATED
    return ScheduleResponse.model_validate(result)
