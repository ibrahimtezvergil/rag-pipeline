from uuid import uuid4

import pytest

from workers.tasks.evaluations import run_evaluation_job


@pytest.mark.asyncio
async def test_run_evaluation_job_processes_run():
    calls: list[str] = []
    run_id = str(uuid4())

    class FakeEvaluationService:
        async def process_run(self, run_uuid):
            calls.append(str(run_uuid))
            return {"run_id": str(run_uuid), "status": "completed"}

    result = await run_evaluation_job(
        {"evaluation_service": FakeEvaluationService()},
        {"run_id": run_id},
    )

    assert result == {"run_id": run_id, "status": "completed"}
    assert calls == [run_id]
