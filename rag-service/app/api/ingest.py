from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.ingest import (
    IngestBatchRequest,
    IngestBatchResponse,
    IngestRequest,
    IngestResponse,
    IngestStatusResponse,
)
from app.services.ingestion import IngestionService


router = APIRouter()


def _parse_project_id(raw_project_id: str) -> uuid.UUID:
    return uuid.UUID(raw_project_id)


def _get_ingestion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> IngestionService:
    service = getattr(request.app.state, "ingestion_service", None)
    if service is not None:
        return service

    dispatcher = getattr(request.app.state, "ingestion_dispatcher", None)
    return IngestionService(session, dispatcher=dispatcher)


@router.post("/ingest", response_model=IngestResponse)
async def create_ingest(
    request: Request,
    response: Response,
    payload: IngestRequest,
    mode: Literal["sync", "async"] | None = Query(default=None),
    service: IngestionService = Depends(_get_ingestion_service),
):
    if mode is not None:
        payload = payload.model_copy(update={"mode": mode})

    project_id = _parse_project_id(request.state.project_id)
    result = await service.create_ingestion_job(payload, project_id)

    response.status_code = (
        status.HTTP_201_CREATED if result["mode"] == "sync" else status.HTTP_202_ACCEPTED
    )
    return IngestResponse.model_validate(result)


@router.post("/ingest/batch", response_model=IngestBatchResponse)
async def create_ingest_batch(
    request: Request,
    response: Response,
    payload: IngestBatchRequest,
    service: IngestionService = Depends(_get_ingestion_service),
):
    if any(item.mode != "async" for item in payload.items):
        raise HTTPException(status_code=400, detail="Batch ingestion only supports async mode")

    project_id = _parse_project_id(request.state.project_id)
    items = await service.create_ingestion_batch(payload.items, project_id)

    response.status_code = status.HTTP_202_ACCEPTED
    return IngestBatchResponse(items=[IngestResponse.model_validate(item) for item in items])


@router.get("/ingest/{job_id}", response_model=IngestStatusResponse)
async def get_ingest_status(
    request: Request,
    job_id: str,
    service: IngestionService = Depends(_get_ingestion_service),
):
    result = await service.get_ingestion_job(job_id)
    return IngestStatusResponse.model_validate(result)


@router.delete("/ingest/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ingest(
    request: Request,
    job_id: str,
    service: IngestionService = Depends(_get_ingestion_service),
):
    await service.delete_ingestion_job(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
