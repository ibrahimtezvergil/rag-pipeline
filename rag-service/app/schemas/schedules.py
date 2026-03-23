from datetime import datetime

from pydantic import BaseModel

from app.schemas.ingest import IngestRequest


class ScheduleCreateRequest(BaseModel):
    cron_expr: str
    ingest: IngestRequest


class ScheduleResponse(BaseModel):
    schedule_id: str
    status: str
    cron_expr: str
    next_run_at: datetime
    source_type: str
    source_ref: str | None = None
