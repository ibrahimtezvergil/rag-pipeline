from __future__ import annotations

from arq import cron
from arq.connections import RedisSettings
from arq.worker import Retry, func

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.evaluations import EvaluationService
from app.services.callbacks import send_ingestion_callback
from app.services.ingestion import IngestionService
from workers.tasks.evaluations import run_evaluation_job
from workers.tasks.schedules import run_schedule_tick


MAX_RETRIES = 3


async def run_ingest_job(ctx: dict[str, object], payload: dict[str, str]) -> dict[str, str]:
    service = ctx.get("ingestion_service")
    if service is None:
        service = IngestionService(AsyncSessionLocal())

    assert isinstance(service, IngestionService)
    job_try = int(ctx.get("job_try", 1))
    try:
        result = await service.process_ingestion_job(
            payload["ingestion_job_id"],
            retry_count=max(0, job_try - 1),
        )
        await _send_callback_if_configured(
            payload,
            status=result["status"],
        )
        return result
    except Exception as exc:
        if job_try >= MAX_RETRIES:
            await service.record_failure(
                payload["ingestion_job_id"],
                retry_count=job_try,
                error_message=str(exc),
            )
            await _send_callback_if_configured(
                payload,
                status="failed",
                error_message=str(exc),
            )
            return {
                "document_id": payload["document_id"],
                "ingestion_job_id": payload["ingestion_job_id"],
                "status": "failed",
            }

        await service.record_retry(
            payload["ingestion_job_id"],
            retry_count=job_try,
            error_message=str(exc),
        )
        raise Retry(defer=2 ** (job_try - 1)) from exc


async def run_stale_reembed_scan(ctx: dict[str, object]) -> dict[str, int]:
    service = ctx.get("ingestion_service")
    if service is None:
        service = IngestionService(AsyncSessionLocal())

    return await service.requeue_stale_documents(limit=100)


async def _send_callback_if_configured(
    payload: dict[str, str],
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    callback_url = payload.get("callback_url")
    if not callback_url:
        return
    try:
        await send_ingestion_callback(
            callback_url=callback_url,
            document_id=payload["document_id"],
            ingestion_job_id=payload["ingestion_job_id"],
            project_id=payload["application_id"],
            status=status,
            source_type=payload["source_type"],
            error_message=error_message,
        )
    except Exception:
        return


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [
        func(run_ingest_job, max_tries=MAX_RETRIES),
        func(run_evaluation_job, max_tries=1),
        func(run_schedule_tick, max_tries=1),
        func(run_stale_reembed_scan, max_tries=1),
    ]
    cron_jobs = [
        cron(run_schedule_tick, name="run_schedule_tick", minute=set(range(60)), second=0),
        cron(run_stale_reembed_scan, name="run_stale_reembed_scan", minute=0, second=0),
    ]
    retry_jobs = True
