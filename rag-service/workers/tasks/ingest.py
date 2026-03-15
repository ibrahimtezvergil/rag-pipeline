from __future__ import annotations

from arq.connections import RedisSettings
from arq.worker import Retry, func

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.ingestion import IngestionService


MAX_RETRIES = 3


async def run_ingest_job(ctx: dict[str, object], payload: dict[str, str]) -> dict[str, str]:
    service = ctx.get("ingestion_service")
    if service is None:
        service = IngestionService(AsyncSessionLocal())

    assert isinstance(service, IngestionService)
    job_try = int(ctx.get("job_try", 1))
    try:
        return await service.process_ingestion_job(
            payload["ingestion_job_id"],
            retry_count=max(0, job_try - 1),
        )
    except Exception as exc:
        if job_try >= MAX_RETRIES:
            await service.record_failure(
                payload["ingestion_job_id"],
                retry_count=job_try,
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


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions = [func(run_ingest_job, max_tries=MAX_RETRIES)]
    retry_jobs = True
