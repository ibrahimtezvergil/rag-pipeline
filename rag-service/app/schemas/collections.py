from pydantic import BaseModel, Field


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")


class CollectionItem(BaseModel):
    name: str
    dimension: int


class CollectionListResponse(BaseModel):
    items: list[CollectionItem]


class CollectionCreateResponse(BaseModel):
    name: str
    dimension: int
    status: str
