from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.services.evaluations import EvaluationService


@pytest.mark.asyncio
async def test_evaluation_service_scores_completed_run():
    run_id = uuid4()
    project_id = uuid4()

    class FakeSample:
        def __init__(self, question, ground_truth, reference_context):
            self.question = question
            self.ground_truth = ground_truth
            self.reference_context = reference_context

    class FakeRepo:
        def __init__(self):
            self.samples = [
                FakeSample(
                    "Which invoice was paid?",
                    "INV-1001 was paid.",
                    "Invoice INV-1001 status is paid.",
                )
            ]
            self.sample_updates = []
            self.run_update = None

        async def get_run(self, run_uuid):
            return SimpleNamespace(id=run_uuid, project_id=project_id, status="pending")

        async def list_samples(self, run_uuid):
            return self.samples

        async def update_sample_result(self, sample, **kwargs):
            self.sample_updates.append(kwargs)

        async def update_run_result(self, run, **kwargs):
            self.run_update = kwargs

    class FakeQueryService:
        async def answer_question(self, question, project_id, **kwargs):
            return {
                "answer": "INV-1001 was paid.",
                "retrieval_context": [
                    {"title": "doc", "snippet": "Invoice INV-1001 status is paid.", "parent_context": ""}
                ],
                "sources": [],
                "retrieval_mode": "hybrid_rrf",
            }

    repo = FakeRepo()
    service = EvaluationService(
        repository=repo,
        query_service=FakeQueryService(),
    )

    result = await service.process_run(run_id)

    assert result["status"] == "completed"
    assert repo.sample_updates
    assert repo.run_update["completed_count"] == 1
    assert repo.run_update["faithfulness_avg"] >= 0


def test_evaluation_service_scores_context_recall():
    service = EvaluationService(repository=None, query_service=None)

    score = service._score_context_recall(
        reference_context="Invoice INV-1001 status paid",
        retrieved_context="Invoice INV-1001 status paid in the CRM export",
    )

    assert score > 0.5
