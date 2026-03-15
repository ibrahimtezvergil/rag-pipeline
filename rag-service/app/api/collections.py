from fastapi import APIRouter, Request, Response, status

from app.schemas.collections import (
    CollectionCreateRequest,
    CollectionCreateResponse,
    CollectionListResponse,
)
from app.services.collections import CollectionsService


router = APIRouter()


def _get_collections_service(request: Request):
    service = getattr(request.app.state, "collections_service", None)
    if service is not None:
        return service
    return CollectionsService()


@router.get("/collections", response_model=CollectionListResponse)
async def list_collections(request: Request):
    result = await _get_collections_service(request).list_collections()
    return CollectionListResponse.model_validate(result)


@router.post("/collections", response_model=CollectionCreateResponse)
async def create_collection(
    request: Request,
    response: Response,
    payload: CollectionCreateRequest,
):
    result = await _get_collections_service(request).create_collection(payload.name)
    response.status_code = status.HTTP_201_CREATED
    return CollectionCreateResponse.model_validate(result)
