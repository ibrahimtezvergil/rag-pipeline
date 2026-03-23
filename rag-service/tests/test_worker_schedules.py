from datetime import UTC, datetime

import pytest

from workers.tasks.schedules import run_schedule_tick


@pytest.mark.asyncio
async def test_run_schedule_tick_processes_due_schedules():
    calls: list[datetime] = []

    class FakeScheduleService:
        async def run_due_schedules(self, *, now):
            calls.append(now)
            return {"scheduled_count": 2}

    result = await run_schedule_tick(
        {
            "schedule_service": FakeScheduleService(),
            "enqueue_time": datetime(2026, 3, 23, 10, 0, tzinfo=UTC),
        }
    )

    assert result == {"scheduled_count": 2}
    assert calls == [datetime(2026, 3, 23, 10, 0, tzinfo=UTC)]
