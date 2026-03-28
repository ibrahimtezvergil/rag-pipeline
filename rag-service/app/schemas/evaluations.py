from pydantic import BaseModel, Field


class EvaluationSampleRequest(BaseModel):
    question: str = Field(min_length=1)
    ground_truth: str = Field(min_length=1)
    reference_context: str = Field(min_length=1)


class EvaluationCreateRequest(BaseModel):
    dataset_name: str = Field(min_length=1)
    samples: list[EvaluationSampleRequest] = Field(min_length=1)


class EvaluationRunResponse(BaseModel):
    run_id: str
    status: str
    dataset_name: str
    sample_count: int
    completed_count: int | None = None
    faithfulness_avg: float | None = None
    answer_relevancy_avg: float | None = None
    context_recall_avg: float | None = None
