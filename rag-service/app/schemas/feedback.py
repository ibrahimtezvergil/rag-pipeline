from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    rating: Literal["up", "down"]
    chunk_ids: list[UUID] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2000)
    query_hash: str | None = Field(default=None, max_length=128)


class FeedbackCreateResponse(BaseModel):
    status: Literal["recorded"]
    rating: Literal["up", "down"]
    recorded_count: int
