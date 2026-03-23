import json
import logging

from app.services import observability as observability_module


def test_emit_event_writes_json_payload_to_logger(caplog):
    with caplog.at_level(logging.INFO, logger="app.observability"):
        observability_module.emit_event(
            "query.completed",
            {
                "project_id": "project-1",
                "source_count": 2,
            },
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "query.completed"
    assert payload["project_id"] == "project-1"
    assert payload["source_count"] == 2
    assert "timestamp" in payload


def test_hash_query_is_deterministic_and_scoped():
    first = observability_module.hash_query(
        question="Revenue in Q1?",
        tenant_id="tenant-1",
        project_id="project-1",
    )
    second = observability_module.hash_query(
        question="Revenue in Q1?",
        tenant_id="tenant-1",
        project_id="project-1",
    )
    different = observability_module.hash_query(
        question="Revenue in Q1?",
        tenant_id="tenant-2",
        project_id="project-1",
    )

    assert first == second
    assert first != different
    assert len(first) == 64
