from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.query import ChatRequest, ChatResponse, QueryRequest, QueryResponse
from app.services.chat import ChatService, create_default_chat_store
from app.services.query import QueryService


router = APIRouter()


def _parse_project_id(raw_project_id: str) -> uuid.UUID:
    return uuid.UUID(raw_project_id)


def _get_query_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> QueryService:
    service = getattr(request.app.state, "query_service", None)
    if service is not None:
        return service
    return QueryService(session)


def _get_chat_service(
    request: Request,
    query_service: QueryService = Depends(_get_query_service),
) -> ChatService:
    service = getattr(request.app.state, "chat_service", None)
    if service is not None:
        return service
    store = getattr(request.app.state, "chat_store", None) or create_default_chat_store()
    return ChatService(query_service, store)


@router.post("/query", response_model=QueryResponse)
async def query(
    request: Request,
    payload: QueryRequest,
    service: QueryService = Depends(_get_query_service),
):
    project_id = _parse_project_id(request.state.project_id)
    result = await service.answer_question(
        payload.question,
        project_id,
        retrieval_mode=payload.retrieval_mode,
        collections=payload.collections,
        merge_strategy=payload.merge_strategy,
        exclude_sources=payload.exclude_sources,
        exclude_documents=payload.exclude_documents,
        acl=payload.acl,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        entity_id=payload.entity_id,
        snapshot_date=payload.snapshot_date,
        tags=payload.tags,
    )
    return QueryResponse.model_validate(result)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    payload: ChatRequest,
    service: ChatService = Depends(_get_chat_service),
):
    project_id = _parse_project_id(request.state.project_id)
    result = await service.reply(
        payload.message,
        project_id,
        session_id=payload.session_id,
    )
    return ChatResponse.model_validate(result)
