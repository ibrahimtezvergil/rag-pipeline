from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import RagEvaluationRun, RagEvaluationSample, RagProject


class EvaluationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project(self, project_id: uuid.UUID) -> RagProject | None:
        return await self.session.get(RagProject, project_id)

    async def create_run(
        self,
        *,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        dataset_name: str,
        sample_count: int,
    ) -> RagEvaluationRun:
        run = RagEvaluationRun(
            project_id=project_id,
            tenant_id=tenant_id,
            dataset_name=dataset_name,
            status="pending",
            sample_count=sample_count,
            completed_count=0,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def create_samples(
        self,
        *,
        run_id: uuid.UUID,
        samples: list[dict[str, str]],
    ) -> list[RagEvaluationSample]:
        rows: list[RagEvaluationSample] = []
        for sample in samples:
            row = RagEvaluationSample(
                run_id=run_id,
                question=sample["question"],
                ground_truth=sample["ground_truth"],
                reference_context=sample["reference_context"],
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def get_run(self, run_id: uuid.UUID) -> RagEvaluationRun | None:
        return await self.session.get(RagEvaluationRun, run_id)

    async def list_samples(self, run_id: uuid.UUID) -> list[RagEvaluationSample]:
        result = await self.session.scalars(
            select(RagEvaluationSample)
            .where(RagEvaluationSample.run_id == run_id)
            .order_by(RagEvaluationSample.created_at, RagEvaluationSample.id)
        )
        return list(result)

    async def update_sample_result(self, sample: RagEvaluationSample, **kwargs) -> RagEvaluationSample:
        for key, value in kwargs.items():
            setattr(sample, key, value)
        await self.session.flush()
        return sample

    async def update_run_result(self, run: RagEvaluationRun, **kwargs) -> RagEvaluationRun:
        for key, value in kwargs.items():
            setattr(run, key, value)
        run.completed_at = datetime.now(UTC)
        await self.session.flush()
        return run

    async def mark_run_running(self, run: RagEvaluationRun) -> RagEvaluationRun:
        run.status = "running"
        await self.session.flush()
        return run

    async def commit(self) -> None:
        await self.session.commit()
