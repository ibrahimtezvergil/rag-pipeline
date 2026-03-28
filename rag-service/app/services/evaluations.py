from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.evaluations import EvaluationRepository
from app.schemas.evaluations import EvaluationCreateRequest
from app.services.dispatch import NullEvaluationDispatcher
from app.services.query import QueryService


class EvaluationService:
    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        repository: EvaluationRepository | None = None,
        query_service: QueryService | None = None,
        dispatcher: NullEvaluationDispatcher | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or EvaluationRepository(session)
        self.query_service = query_service or (QueryService(session) if session is not None else None)
        self.dispatcher = dispatcher or NullEvaluationDispatcher()

    async def create_run(
        self,
        payload: EvaluationCreateRequest,
        project_id: uuid.UUID,
    ) -> dict[str, object]:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        run = await self.repository.create_run(
            project_id=project.id,
            tenant_id=project.tenant_id,
            dataset_name=payload.dataset_name,
            sample_count=len(payload.samples),
        )
        await self.repository.create_samples(
            run_id=run.id,
            samples=[sample.model_dump() for sample in payload.samples],
        )
        await self.repository.commit()
        await self.dispatcher.enqueue({"run_id": str(run.id)})
        return {
            "run_id": str(run.id),
            "status": run.status,
            "dataset_name": run.dataset_name,
            "sample_count": run.sample_count,
        }

    async def get_run(self, run_id: str, project_id: uuid.UUID) -> dict[str, object]:
        run_uuid = uuid.UUID(run_id)
        run = await self.repository.get_run(run_uuid)
        if run is None or run.project_id != project_id:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return {
            "run_id": str(run.id),
            "status": run.status,
            "dataset_name": run.dataset_name,
            "sample_count": run.sample_count,
            "completed_count": run.completed_count,
            "faithfulness_avg": run.faithfulness_avg,
            "answer_relevancy_avg": run.answer_relevancy_avg,
            "context_recall_avg": run.context_recall_avg,
        }

    async def process_run(self, run_id: uuid.UUID) -> dict[str, object]:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        if self.query_service is None:
            raise RuntimeError("Query service is not configured")

        await self._maybe_call_repository("mark_run_running", run)
        samples = await self.repository.list_samples(run.id)
        faithfulness_scores: list[float] = []
        answer_relevancy_scores: list[float] = []
        context_recall_scores: list[float] = []
        completed_count = 0

        for sample in samples:
            try:
                result = await self.query_service.answer_question(sample.question, run.project_id)
                retrieved_context = self._join_retrieved_context(result.get("retrieval_context", []))
                model_answer = str(result.get("answer", ""))
                faithfulness = self._score_faithfulness(model_answer, retrieved_context)
                answer_relevancy = self._score_answer_relevancy(sample.ground_truth, model_answer)
                context_recall = self._score_context_recall(sample.reference_context, retrieved_context)
                await self.repository.update_sample_result(
                    sample,
                    model_answer=model_answer,
                    retrieved_context=retrieved_context,
                    faithfulness_score=faithfulness,
                    answer_relevancy_score=answer_relevancy,
                    context_recall_score=context_recall,
                    error_message=None,
                )
                faithfulness_scores.append(faithfulness)
                answer_relevancy_scores.append(answer_relevancy)
                context_recall_scores.append(context_recall)
            except Exception as exc:
                await self.repository.update_sample_result(
                    sample,
                    model_answer=None,
                    retrieved_context=None,
                    faithfulness_score=None,
                    answer_relevancy_score=None,
                    context_recall_score=None,
                    error_message=str(exc),
                )
            completed_count += 1

        await self.repository.update_run_result(
            run,
            status="completed",
            completed_count=completed_count,
            faithfulness_avg=self._average(faithfulness_scores),
            answer_relevancy_avg=self._average(answer_relevancy_scores),
            context_recall_avg=self._average(context_recall_scores),
        )
        await self._maybe_call_repository("commit")
        return {
            "run_id": str(run.id),
            "status": "completed",
        }

    async def _maybe_call_repository(self, method_name: str, *args: object) -> None:
        method = getattr(self.repository, method_name, None)
        if method is None:
            return
        await method(*args)

    def _average(self, scores: list[float]) -> float | None:
        if not scores:
            return None
        return sum(scores) / len(scores)

    def _join_retrieved_context(self, blocks: list[dict[str, object]]) -> str:
        return " ".join(
            " ".join(
                part for part in [
                    str(block.get("title", "")).strip(),
                    str(block.get("snippet", "")).strip(),
                    str(block.get("parent_context", "")).strip(),
                ] if part
            )
            for block in blocks
        ).strip()

    def _score_answer_relevancy(self, ground_truth: str, answer: str) -> float:
        return self._overlap_score(ground_truth, answer)

    def _score_context_recall(self, reference_context: str, retrieved_context: str) -> float:
        return self._overlap_score(reference_context, retrieved_context)

    def _score_faithfulness(self, answer: str, retrieved_context: str) -> float:
        return self._overlap_score(answer, retrieved_context)

    def _overlap_score(self, expected: str, actual: str) -> float:
        expected_terms = set(self._terms(expected))
        if not expected_terms:
            return 0.0
        actual_terms = set(self._terms(actual))
        if not actual_terms:
            return 0.0
        return len(expected_terms & actual_terms) / len(expected_terms)

    def _terms(self, text: str) -> list[str]:
        return [
            term
            for term in re.findall(r"[A-Za-z0-9]+", text.lower())
            if len(term) >= 3 or any(ch.isdigit() for ch in term)
        ]
