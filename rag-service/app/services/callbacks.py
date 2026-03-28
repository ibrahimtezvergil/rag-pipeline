from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.config import get_settings


def build_ingestion_callback_payload(
    *,
    document_id: str,
    ingestion_job_id: str,
    project_id: str,
    status: str,
    source_type: str,
    error_message: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "document_id": document_id,
        "ingestion_job_id": ingestion_job_id,
        "project_id": project_id,
        "status": status,
        "source_type": source_type,
    }
    if error_message:
        payload["error_message"] = error_message
    return payload


def sign_ingestion_callback(body: bytes) -> str:
    secret = get_settings().ingest_callback_secret.encode("utf-8")
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


async def send_ingestion_callback(
    *,
    callback_url: str,
    document_id: str,
    ingestion_job_id: str,
    project_id: str,
    status: str,
    source_type: str,
    error_message: str | None = None,
) -> int | None:
    payload = build_ingestion_callback_payload(
        document_id=document_id,
        ingestion_job_id=ingestion_job_id,
        project_id=project_id,
        status=status,
        source_type=source_type,
        error_message=error_message,
    )
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = sign_ingestion_callback(body)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.post(
                callback_url,
                content=body,
                headers={
                    "content-type": "application/json",
                    "X-RAG-Signature": signature,
                },
            )
            return response.status_code
    except Exception:
        return None
