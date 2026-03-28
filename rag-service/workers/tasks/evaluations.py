from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from app.db.session import AsyncSessionLocal
from app.services.evaluations import EvaluationService


async def run_evaluation_job(ctx: dict[str, object], payload: dict[str, str]) -> dict[str, object]:
    service = ctx.get("evaluation_service")
    if service is None:
        service = EvaluationService(AsyncSessionLocal())
    process_run: Callable[[uuid.UUID], Awaitable[dict[str, object]]] | None = getattr(service, "process_run", None)
    if process_run is None:
        raise TypeError("evaluation_service must provide process_run(run_id)")
    return await process_run(uuid.UUID(payload["run_id"]))
