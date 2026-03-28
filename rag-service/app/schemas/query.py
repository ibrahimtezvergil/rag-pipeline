from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    retrieval_mode: Literal["dense", "sparse", "hybrid"] = "hybrid"
    collections: list[str] | None = None
    merge_strategy: Literal["rrf"] = "rrf"
    exclude_sources: list[str] | None = None
    exclude_documents: list[str] | None = None
    acl: list[str] | None = None
    scope_type: str | None = None
    scope_id: str | None = None
    entity_id: str | None = None
    snapshot_date: str | None = None
    tags: list[str] | None = None


class QuerySource(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    title: str
    source_ref: str
    snippet: str
    score: float | None = None


class RetrievalContextBlock(BaseModel):
    title: str
    snippet: str
    parent_context: str = ""
    score: float | None = None


class QueryResponse(BaseModel):
    answer: str
    retrieval_mode: str
    confidence_score: float | None = None
    confidence_warning: str | None = None
    retrieval_context: list[RetrievalContextBlock]
    sources: list[QuerySource]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    retrieval_mode: str
    confidence_score: float | None = None
    confidence_warning: str | None = None
    retrieval_context: list[RetrievalContextBlock]
    sources: list[QuerySource]
