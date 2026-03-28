from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.db import RagSchedule, RagSyncCheckpoint
from app.schemas.schedules import ScheduleCreateRequest
from app.services.schedules import ScheduleService, next_cron_run_after


@pytest.mark.asyncio
async def test_create_schedule_persists_schedule_row(
    integration_session,
    seeded_application,
):
    service = ScheduleService(integration_session, ingestion_service=SimpleNamespace())

    result = await service.create_schedule(
        ScheduleCreateRequest(
            cron_expr="*/30 * * * *",
            ingest={
                "source_type": "web",
                "source_ref": "https://example.com/article",
                "source_connector_id": "00000000-0000-0000-0000-000000000111",
            },
        ),
        seeded_application["application_id"],
    )

    schedule = await service.repository.get_schedule(UUID(result["schedule_id"]))
    assert schedule is not None
    assert schedule.application_id == seeded_application["application_id"]
    assert schedule.tenant_id == seeded_application["tenant_id"]
    assert schedule.cron_expr == "*/30 * * * *"
    assert schedule.source_type == "web"
    assert schedule.source_ref == "https://example.com/article"
    assert schedule.enabled is True
    assert schedule.next_run_at is not None


@pytest.mark.asyncio
async def test_run_due_schedules_creates_async_ingestion_with_checkpoint(
    integration_session,
    seeded_application,
):
    calls: list[tuple[object, object]] = []

    class FakeIngestionService:
        async def create_ingestion_job(self, payload, application_id):
            calls.append((payload, application_id))
            return {
                "document_id": "doc-1",
                "ingestion_job_id": "job-1",
                "status": "pending",
                "mode": payload.mode,
                "source_type": payload.source_type,
            }

    service = ScheduleService(integration_session, ingestion_service=FakeIngestionService())
    schedule = await service.repository.upsert_schedule(
        application_id=seeded_application["application_id"],
        tenant_id=seeded_application["tenant_id"],
        source_type="web",
        source_ref="https://example.com/article",
        source_connector_id=UUID("00000000-0000-0000-0000-000000000111"),
        cron_expr="*/30 * * * *",
        payload={
            "source_type": "web",
            "source_ref": "https://example.com/article",
        },
        next_run_at=datetime(2026, 3, 23, 10, 0, tzinfo=UTC),
    )
    integration_session.add(
        RagSyncCheckpoint(
            source_connector_id=UUID("00000000-0000-0000-0000-000000000111"),
            cursor_state={"cursor": "abc"},
            last_synced_at=datetime(2026, 3, 23, 9, 30, tzinfo=UTC),
        )
    )
    await integration_session.commit()

    result = await service.run_due_schedules(now=datetime(2026, 3, 23, 10, 0, tzinfo=UTC))

    assert result == {"scheduled_count": 1}
    payload, application_id = calls[0]
    assert application_id == seeded_application["application_id"]
    assert payload.mode == "async"
    assert payload.cursor_state == {"cursor": "abc"}
    assert payload.source_connector_id == "00000000-0000-0000-0000-000000000111"

    refreshed = await service.repository.get_schedule(schedule.id)
    assert refreshed is not None
    assert refreshed.last_run_at == datetime(2026, 3, 23, 10, 0, tzinfo=UTC)
    assert refreshed.next_run_at == datetime(2026, 3, 23, 10, 30, tzinfo=UTC)


def test_next_cron_run_after_supports_step_and_fixed_fields():
    start = datetime(2026, 3, 23, 10, 5, tzinfo=UTC)

    assert next_cron_run_after("*/15 * * * *", start) == datetime(2026, 3, 23, 10, 15, tzinfo=UTC)
    assert next_cron_run_after("30 12 * * *", start) == datetime(2026, 3, 23, 12, 30, tzinfo=UTC)


def test_next_cron_run_after_rejects_invalid_expression():
    with pytest.raises(ValueError):
        next_cron_run_after("invalid", datetime(2026, 3, 23, 10, 0, tzinfo=UTC))
