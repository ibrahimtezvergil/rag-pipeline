from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


SourceType = Literal["pdf", "web", "db", "structured", "image"]
IngestMode = Literal["sync", "async"]


class IngestRequest(BaseModel):
    source_type: SourceType
    source_ref: HttpUrl | None = None
    source_base64: str | None = None
    source_filename: str | None = None
    source_sql: str | None = None
    title: str | None = None
    records: list[dict] | None = None
    origin: str | None = None
    scope_type: str | None = None
    scope_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    record_ids: list[str] | None = None
    snapshot_date: str | None = None
    tags: list[str] | None = None
    mode: IngestMode = "async"

    @model_validator(mode="after")
    def validate_source_input(self):
        has_url = self.source_ref is not None
        has_base64 = bool(self.source_base64)
        has_sql = bool(self.source_sql)
        has_records = bool(self.records)
        input_count = sum([has_url, has_base64, has_sql, has_records])
        if input_count != 1:
            raise ValueError(
                "Provide exactly one of source_ref, source_base64, source_sql, or records"
            )
        if has_base64 and not self.source_filename:
            raise ValueError("source_filename is required when source_base64 is provided")
        if has_sql and self.source_type != "db":
            raise ValueError("source_sql is only supported for db source_type")
        if self.source_type == "db" and not has_sql:
            raise ValueError("db source_type requires source_sql")
        if has_records and self.source_type != "structured":
            raise ValueError("records are only supported for structured source_type")
        if self.source_type == "structured" and not has_records:
            raise ValueError("structured source_type requires records")
        if self.source_type == "image" and not (has_url or has_base64):
            raise ValueError("image source_type requires source_ref or source_base64")
        return self


class IngestBatchRequest(BaseModel):
    items: list[IngestRequest] = Field(min_length=1, max_length=100)


class IngestResponse(BaseModel):
    document_id: str
    ingestion_job_id: str
    status: str
    mode: IngestMode
    source_type: SourceType


class IngestBatchResponse(BaseModel):
    items: list[IngestResponse]


class IngestStatusResponse(BaseModel):
    document_id: str
    ingestion_job_id: str
    status: str
    job_type: str
    source_type: SourceType
