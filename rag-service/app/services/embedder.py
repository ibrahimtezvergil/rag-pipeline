from __future__ import annotations

import asyncio
import base64

import httpx

from app.config import get_settings


async def prepare_pdf_embedding(source_ref: str, metadata: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    return {
        "provider": "gemini",
        "model": settings.embed_model,
        "task_type": "RETRIEVAL_DOCUMENT",
        "status": "prepared",
        "source_ref": source_ref,
        "page_count": metadata.get("page_count"),
    }


async def resolve_pdf_embedding(
    source_ref: str,
    content: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    settings = get_settings()
    if settings.gemini_api_key.strip() and content.strip():
        return await embed_pdf_document(
            content=content,
            title=str(metadata.get("title") or source_ref),
        )

    return await prepare_pdf_embedding(source_ref, metadata)


async def embed_pdf_document(content: str, title: str) -> dict[str, object]:
    return await embed_text_content(
        content=content,
        title=title,
        task_type="RETRIEVAL_DOCUMENT",
    )


async def embed_query_text(content: str) -> dict[str, object]:
    return await embed_text_content(
        content=content,
        title="query",
        task_type="RETRIEVAL_QUERY",
    )


async def embed_image_content(
    *,
    image_bytes: bytes,
    title: str,
    mime_type: str,
) -> dict[str, object]:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return await _embed_parts(
        parts=[
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": encoded,
                }
            }
        ],
        title=title,
        task_type="RETRIEVAL_DOCUMENT",
    )


async def embed_audio_content(
    *,
    audio_bytes: bytes,
    title: str,
    mime_type: str,
) -> dict[str, object]:
    encoded = base64.b64encode(audio_bytes).decode("utf-8")
    return await _embed_parts(
        parts=[
            {
                "inlineData": {
                    "mimeType": mime_type,
                    "data": encoded,
                }
            }
        ],
        title=title,
        task_type="RETRIEVAL_DOCUMENT",
    )


async def embed_text_content(
    content: str,
    title: str,
    *,
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> dict[str, object]:
    return await _embed_parts(
        parts=[{"text": content}],
        title=title,
        task_type=task_type,
    )


async def _embed_parts(
    *,
    parts: list[dict[str, object]],
    title: str,
    task_type: str,
) -> dict[str, object]:
    settings = get_settings()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.embed_model}:embedContent"
    )
    payload = {
        "model": f"models/{settings.embed_model}",
        "content": {"parts": parts},
        "taskType": task_type,
        "title": title,
        "outputDimensionality": settings.embed_dimension,
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    response = await _post_with_retry(url, headers=headers, payload=payload)

    values = response.json()["embedding"]["values"]
    return {
        "provider": "gemini",
        "model": settings.embed_model,
        "task_type": task_type,
        "embed_version": f"{settings.embed_model}-{settings.embed_dimension}",
        "status": "completed",
        "values": values,
        "dimension": len(values),
        "vector_dimension": len(values),
    }


async def _post_with_retry(url: str, *, headers: dict[str, str], payload: dict[str, object]):
    delays = [1, 2, 4]
    last_error: Exception | None = None

    for attempt in range(len(delays) + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code != 429 or attempt >= len(delays):
                raise
            await asyncio.sleep(delays[attempt])

    assert last_error is not None
    raise last_error
