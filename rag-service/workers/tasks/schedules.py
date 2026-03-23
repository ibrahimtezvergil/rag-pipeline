from __future__ import annotations

from datetime import UTC, datetime

from app.db.session import AsyncSessionLocal
from app.services.schedules import ScheduleService


async def run_schedule_tick(ctx: dict[str, object]) -> dict[str, int]:
    service = ctx.get("schedule_service")
    if service is None:
        service = ScheduleService(AsyncSessionLocal())
    run_at = ctx.get("enqueue_time")
    if not isinstance(run_at, datetime):
        run_at = datetime.now(UTC)
    return await service.run_due_schedules(now=run_at)
