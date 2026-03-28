from fastapi import APIRouter, Depends

from app.api.collections import router as collections_router
from app.api.evaluations import router as evaluations_router
from app.api.feedback import router as feedback_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.query import router as query_router
from app.api.schedules import router as schedules_router
from app.deps import RequestContext, get_request_context


api_router = APIRouter()
api_router.include_router(collections_router)
api_router.include_router(evaluations_router)
api_router.include_router(feedback_router)
api_router.include_router(health_router)
api_router.include_router(ingest_router)
api_router.include_router(query_router)
api_router.include_router(schedules_router)


@api_router.get("/protected")
async def protected_endpoint(
    context: RequestContext = Depends(get_request_context),
) -> dict[str, str]:
    return {"project_id": context.project_id, "status": "authorized"}
