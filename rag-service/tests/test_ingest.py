from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_post_ingest_accepts_pdf_async(client, app, valid_headers):
    document_id = str(uuid4())
    job_id = str(uuid4())

    async def create_ingestion_job(payload, project_id):
        assert payload.source_type == "pdf"
        assert str(payload.source_ref) == "https://example.com/doc.pdf"
        assert payload.mode == "async"
        assert str(project_id) == valid_headers["X-Project-ID"]
        return {
            "document_id": document_id,
            "ingestion_job_id": job_id,
            "status": "pending",
            "mode": "async",
            "source_type": "pdf",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "pdf",
            "source_ref": "https://example.com/doc.pdf",
            "mode": "async",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "document_id": document_id,
        "ingestion_job_id": job_id,
        "status": "pending",
        "mode": "async",
        "source_type": "pdf",
    }


@pytest.mark.asyncio
async def test_post_ingest_completes_web_sync(client, app, valid_headers):
    async def create_ingestion_job(payload, project_id):
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "completed",
            "mode": "sync",
            "source_type": "web",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "web",
            "source_ref": "https://example.com/article",
            "mode": "sync",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert response.json()["mode"] == "sync"
    assert response.json()["source_type"] == "web"


@pytest.mark.asyncio
async def test_post_ingest_allows_mode_query_param_override(client, app, valid_headers):
    async def create_ingestion_job(payload, project_id):
        assert payload.mode == "sync"
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "completed",
            "mode": "sync",
            "source_type": "pdf",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest?mode=sync",
        headers=valid_headers,
        json={
            "source_type": "pdf",
            "source_ref": "https://example.com/doc.pdf",
            "mode": "async",
        },
    )

    assert response.status_code == 201
    assert response.json()["mode"] == "sync"


@pytest.mark.asyncio
async def test_post_ingest_batch_accepts_multiple_items(client, app, valid_headers):
    async def create_ingestion_batch(items, project_id):
        assert len(items) == 2
        assert str(project_id) == valid_headers["X-Project-ID"]
        return [
            {
                "document_id": str(uuid4()),
                "ingestion_job_id": str(uuid4()),
                "status": "pending",
                "mode": "async",
                "source_type": "pdf",
            },
            {
                "document_id": str(uuid4()),
                "ingestion_job_id": str(uuid4()),
                "status": "pending",
                "mode": "async",
                "source_type": "web",
            },
        ]

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_batch=create_ingestion_batch,
    )

    response = await client.post(
        "/ingest/batch",
        headers=valid_headers,
        json={
            "items": [
                {
                    "source_type": "pdf",
                    "source_ref": "https://example.com/doc.pdf",
                    "mode": "async",
                },
                {
                    "source_type": "web",
                    "source_ref": "https://example.com/article",
                    "mode": "async",
                },
            ]
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["source_type"] == "pdf"
    assert body["items"][1]["source_type"] == "web"


@pytest.mark.asyncio
async def test_get_ingest_status_returns_job(client, app, valid_headers):
    ingestion_job_id = str(uuid4())
    document_id = str(uuid4())

    async def get_ingestion_job(job_id):
        assert job_id == ingestion_job_id
        return {
            "document_id": document_id,
            "ingestion_job_id": ingestion_job_id,
            "status": "pending",
            "job_type": "ingest",
            "source_type": "pdf",
        }

    app.state.ingestion_service = SimpleNamespace(
        get_ingestion_job=get_ingestion_job,
    )

    response = await client.get(f"/ingest/{ingestion_job_id}", headers=valid_headers)

    assert response.status_code == 200
    assert response.json() == {
        "document_id": document_id,
        "ingestion_job_id": ingestion_job_id,
        "status": "pending",
        "job_type": "ingest",
        "source_type": "pdf",
    }


@pytest.mark.asyncio
async def test_delete_ingest_soft_deletes_document(client, app, valid_headers):
    ingestion_job_id = str(uuid4())

    async def delete_ingestion_job(job_id):
        assert job_id == ingestion_job_id
        return None

    app.state.ingestion_service = SimpleNamespace(
        delete_ingestion_job=delete_ingestion_job,
    )

    response = await client.delete(f"/ingest/{ingestion_job_id}", headers=valid_headers)

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_post_ingest_batch_rejects_sync_items(client, valid_headers):
    response = await client.post(
        "/ingest/batch",
        headers=valid_headers,
        json={
            "items": [
                {
                    "source_type": "pdf",
                    "source_ref": "https://example.com/doc.pdf",
                    "mode": "sync",
                }
            ]
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Batch ingestion only supports async mode"


@pytest.mark.asyncio
async def test_post_ingest_rejects_unsupported_source_type(client, valid_headers):
    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "audio",
            "source_ref": "https://example.com/audio.mp3",
            "mode": "async",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_ingest_accepts_base64_pdf_payload(client, app, valid_headers):
    async def create_ingestion_job(payload, project_id):
        assert payload.source_type == "pdf"
        assert payload.source_ref is None
        assert payload.source_base64 == "UERG"
        assert payload.source_filename == "report.pdf"
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "pending",
            "mode": "async",
            "source_type": "pdf",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "pdf",
            "source_base64": "UERG",
            "source_filename": "report.pdf",
            "mode": "async",
        },
    )

    assert response.status_code == 202
    assert response.json()["source_type"] == "pdf"


@pytest.mark.asyncio
async def test_post_ingest_accepts_db_sql_payload(client, app, valid_headers):
    async def create_ingestion_job(payload, project_id):
        assert payload.source_type == "db"
        assert payload.source_sql == "SELECT customer, plan FROM accounts"
        assert payload.source_ref is None
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "pending",
            "mode": "async",
            "source_type": "db",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "db",
            "source_sql": "SELECT customer, plan FROM accounts",
            "mode": "async",
        },
    )

    assert response.status_code == 202
    assert response.json()["source_type"] == "db"


@pytest.mark.asyncio
async def test_post_ingest_accepts_structured_records_payload(client, app, valid_headers):
    async def create_ingestion_job(payload, project_id):
        assert payload.source_type == "structured"
        assert payload.title == "CRM Customer Snapshot"
        assert payload.origin == "crm"
        assert payload.entity_id == "cust_42"
        assert payload.record_ids == ["opp_91", "note_18"]
        assert payload.snapshot_date == "2026-03-15"
        assert payload.records == [
            {
                "customer_id": 42,
                "company_name": "Acme Mobilya",
                "stage": "negotiation",
            }
        ]
        assert payload.scope_type == "customer"
        assert payload.scope_id == "cust_42"
        assert payload.entity_type == "customer"
        assert payload.tags == ["crm", "daily-sync"]
        return {
            "document_id": str(uuid4()),
            "ingestion_job_id": str(uuid4()),
            "status": "pending",
            "mode": "async",
            "source_type": "structured",
        }

    app.state.ingestion_service = SimpleNamespace(
        create_ingestion_job=create_ingestion_job,
    )

    response = await client.post(
        "/ingest",
        headers=valid_headers,
        json={
            "source_type": "structured",
            "title": "CRM Customer Snapshot",
            "origin": "crm",
            "entity_id": "cust_42",
            "record_ids": ["opp_91", "note_18"],
            "snapshot_date": "2026-03-15",
            "records": [
                {
                    "customer_id": 42,
                    "company_name": "Acme Mobilya",
                    "stage": "negotiation",
                }
            ],
            "scope_type": "customer",
            "scope_id": "cust_42",
            "entity_type": "customer",
            "tags": ["crm", "daily-sync"],
            "mode": "async",
        },
    )

    assert response.status_code == 202
    assert response.json()["source_type"] == "structured"
