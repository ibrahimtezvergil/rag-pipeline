from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.schedules import ScheduleRepository
from app.schemas.ingest import IngestRequest
from app.schemas.schedules import ScheduleCreateRequest
from app.services.ingestion import IngestionService


def _parse_cron_field(field: str, *, minimum: int, maximum: int) -> set[int]:
    if field == "*":
        return set(range(minimum, maximum + 1))

    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError("Invalid cron expression")
        if part.startswith("*/"):
            step = int(part[2:])
            if step <= 0:
                raise ValueError("Invalid cron expression")
            values.update(range(minimum, maximum + 1, step))
            continue
        if "-" in part:
            start_raw, end_raw = part.split("-", maxsplit=1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                raise ValueError("Invalid cron expression")
            values.update(range(start, end + 1))
            continue
        value = int(part)
        values.add(value)

    if not values or min(values) < minimum or max(values) > maximum:
        raise ValueError("Invalid cron expression")
    return values


def next_cron_run_after(cron_expr: str, after: datetime) -> datetime:
    parts = cron_expr.split()
    if len(parts) != 5:
        raise ValueError("Invalid cron expression")

    minute_values = _parse_cron_field(parts[0], minimum=0, maximum=59)
    hour_values = _parse_cron_field(parts[1], minimum=0, maximum=23)
    day_values = _parse_cron_field(parts[2], minimum=1, maximum=31)
    month_values = _parse_cron_field(parts[3], minimum=1, maximum=12)
    weekday_values = _parse_cron_field(parts[4], minimum=0, maximum=6)

    candidate = after.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        cron_weekday = (candidate.weekday() + 1) % 7
        if (
            candidate.minute in minute_values
            and candidate.hour in hour_values
            and candidate.day in day_values
            and candidate.month in month_values
            and cron_weekday in weekday_values
        ):
            return candidate
        candidate += timedelta(minutes=1)

    raise ValueError("Invalid cron expression")


class ScheduleService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ingestion_service: IngestionService | None = None,
    ) -> None:
        self.repository = ScheduleRepository(session)
        self.ingestion_service = ingestion_service or IngestionService(session)

    async def create_schedule(
        self,
        payload: ScheduleCreateRequest,
        project_id: uuid.UUID,
    ) -> dict[str, str]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        now = datetime.now(UTC)
        next_run_at = next_cron_run_after(payload.cron_expr, now)
        ingest_payload = payload.ingest.model_dump(mode="json", exclude_none=True)
        ingest_payload["mode"] = "async"
        source_connector_id = (
            uuid.UUID(payload.ingest.source_connector_id)
            if payload.ingest.source_connector_id
            else None
        )
        source_ref = self._source_ref(payload.ingest)
        schedule = await self.repository.upsert_schedule(
            project_id=project.id,
            tenant_id=project.tenant_id,
            source_type=payload.ingest.source_type,
            source_ref=source_ref,
            source_connector_id=source_connector_id,
            cron_expr=payload.cron_expr,
            payload=ingest_payload,
            next_run_at=next_run_at,
        )
        await self.repository.commit()
        return self._serialize_schedule(schedule)

    async def run_due_schedules(self, *, now: datetime | None = None) -> dict[str, int]:
        run_at = (now or datetime.now(UTC)).astimezone(UTC).replace(second=0, microsecond=0)
        due_schedules = await self.repository.list_due_schedules(run_at)

        scheduled_count = 0
        for schedule in due_schedules:
            ingest_payload = dict(schedule.payload_json or {})
            if schedule.source_connector_id is not None:
                checkpoint = await self.repository.get_checkpoint(schedule.source_connector_id)
                if checkpoint is not None and checkpoint.cursor_state:
                    ingest_payload["cursor_state"] = checkpoint.cursor_state
                ingest_payload["source_connector_id"] = str(schedule.source_connector_id)
            ingest_payload["mode"] = "async"
            await self.ingestion_service.create_ingestion_job(
                IngestRequest.model_validate(ingest_payload),
                schedule.project_id,
            )
            await self.repository.mark_schedule_ran(
                schedule,
                run_at=run_at,
                next_run_at=next_cron_run_after(schedule.cron_expr, run_at),
            )
            scheduled_count += 1

        await self.repository.commit()
        return {"scheduled_count": scheduled_count}

    def _source_ref(self, payload: IngestRequest) -> str | None:
        if payload.source_ref is not None:
            return str(payload.source_ref)
        if payload.records is not None:
            return "inline://structured-records"
        if payload.source_sql is not None:
            return "inline://sql-query"
        if payload.source_filename is not None:
            return f"inline://{payload.source_filename}"
        return None

    def _serialize_schedule(self, schedule) -> dict[str, str]:
        return {
            "schedule_id": str(schedule.id),
            "status": "enabled" if schedule.enabled else "disabled",
            "cron_expr": schedule.cron_expr,
            "next_run_at": schedule.next_run_at.isoformat(),
            "source_type": schedule.source_type,
            "source_ref": schedule.source_ref,
        }
