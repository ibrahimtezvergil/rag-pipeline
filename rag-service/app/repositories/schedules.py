from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import RagProject, RagSchedule, RagSyncCheckpoint


class ScheduleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project(self, project_id: uuid.UUID) -> RagProject | None:
        return await self.session.get(RagProject, project_id)

    async def get_schedule(self, schedule_id: uuid.UUID) -> RagSchedule | None:
        return await self.session.get(RagSchedule, schedule_id)

    async def get_checkpoint(self, source_connector_id: uuid.UUID) -> RagSyncCheckpoint | None:
        result = await self.session.scalars(
            select(RagSyncCheckpoint).where(
                RagSyncCheckpoint.source_connector_id == source_connector_id
            )
        )
        return result.first()

    async def upsert_schedule(
        self,
        *,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        source_type: str,
        source_ref: str | None,
        source_connector_id: uuid.UUID | None,
        cron_expr: str,
        payload: dict,
        next_run_at: datetime,
    ) -> RagSchedule:
        result = await self.session.scalars(
            select(RagSchedule).where(
                RagSchedule.project_id == project_id,
                RagSchedule.source_type == source_type,
                RagSchedule.source_ref == source_ref,
                RagSchedule.source_connector_id == source_connector_id,
            )
        )
        schedule = result.first()
        if schedule is None:
            schedule = RagSchedule(
                project_id=project_id,
                tenant_id=tenant_id,
                source_type=source_type,
                source_ref=source_ref,
                source_connector_id=source_connector_id,
                cron_expr=cron_expr,
                payload_json=payload,
                enabled=True,
                next_run_at=next_run_at,
            )
            self.session.add(schedule)
        else:
            schedule.cron_expr = cron_expr
            schedule.payload_json = payload
            schedule.enabled = True
            schedule.next_run_at = next_run_at
        await self.session.flush()
        return schedule

    async def list_due_schedules(self, now: datetime) -> list[RagSchedule]:
        result = await self.session.scalars(
            select(RagSchedule)
            .where(
                RagSchedule.enabled.is_(True),
                RagSchedule.next_run_at <= now,
            )
            .order_by(RagSchedule.next_run_at, RagSchedule.created_at)
        )
        return list(result)

    async def mark_schedule_ran(
        self,
        schedule: RagSchedule,
        *,
        run_at: datetime,
        next_run_at: datetime,
    ) -> RagSchedule:
        schedule.last_run_at = run_at.astimezone(UTC)
        schedule.next_run_at = next_run_at.astimezone(UTC)
        await self.session.flush()
        return schedule

    async def commit(self) -> None:
        await self.session.commit()
