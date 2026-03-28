from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.deps import ingest_batch_rate_limit, ingest_rate_limit
from app.schemas.ingest import (
    IngestBatchRequest,
    IngestBatchResponse,
    IngestRequest,
    IngestResponse,
    IngestStatusResponse,
)
from app.services.ingestion import IngestionService
from app.services.tracing import observe, update_current_observation


router = APIRouter()


def _parse_application_id(raw_application_id: str) -> uuid.UUID:
    return uuid.UUID(raw_application_id)


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
@observe(name="ingest-endpoint", as_type="chain")
async def create_ingest(
    request: Request,
    response: Response,
    payload: IngestRequest,
    mode: Literal["sync", "async"] | None = Query(default=None),
    _: None = Depends(ingest_rate_limit),
    service: IngestionService = Depends(_get_ingestion_service),
):
    if mode is not None:
        payload = payload.model_copy(update={"mode": mode})

    application_id = _parse_application_id(request.state.application_id)
    update_current_observation(
        metadata={
            "application_id": str(application_id),
            "endpoint": "ingest",
            "source_type": payload.source_type,
            "mode": payload.mode,
        }
    )
    result = await service.create_ingestion_job(payload, application_id)

    response.status_code = (
        status.HTTP_201_CREATED if result["mode"] == "sync" else status.HTTP_202_ACCEPTED
    )
    return IngestResponse.model_validate(result)


@router.post("/ingest/batch", response_model=IngestBatchResponse)
@observe(name="ingest-batch-endpoint", as_type="chain")
async def create_ingest_batch(
    request: Request,
    response: Response,
    payload: IngestBatchRequest,
    _: None = Depends(ingest_batch_rate_limit),
    service: IngestionService = Depends(_get_ingestion_service),
):
    if any(item.mode != "async" for item in payload.items):
        raise HTTPException(status_code=400, detail="Batch ingestion only supports async mode")

    application_id = _parse_application_id(request.state.application_id)
    update_current_observation(
        metadata={
            "application_id": str(application_id),
            "endpoint": "ingest_batch",
            "item_count": len(payload.items),
        }
    )
    items = await service.create_ingestion_batch(payload.items, application_id)

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
