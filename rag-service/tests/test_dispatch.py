import pytest

from app.services.dispatch import ArqIngestionDispatcher


class FakeArqRedis:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def enqueue_job(self, function_name, *args, **kwargs):
        self.calls.append(
            {
                "function_name": function_name,
                "args": args,
                "kwargs": kwargs,
            }
        )
        return object()


@pytest.mark.asyncio
async def test_arq_dispatcher_enqueues_named_ingest_job():
    pool = FakeArqRedis()
    dispatcher = ArqIngestionDispatcher(pool=pool)

    payload = {
        "document_id": "doc-1",
        "ingestion_job_id": "job-1",
        "application_id": "project-1",
        "source_type": "pdf",
        "source_ref": "https://example.com/report.pdf",
    }

    await dispatcher.enqueue(payload)

    assert pool.calls == [
        {
            "function_name": "run_ingest_job",
            "args": (payload,),
            "kwargs": {
                "_job_id": "job-1",
            },
        }
    ]
