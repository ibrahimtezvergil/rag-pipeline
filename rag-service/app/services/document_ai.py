from __future__ import annotations

import base64

import httpx

from app.config import get_settings


PROMPT = "Extract the readable text from this PDF document. Return only the plain text content."


async def extract_small_pdf_document(
    pdf_bytes: bytes,
    title: str,
    source_ref: str,
) -> dict[str, object]:
    settings = get_settings()
    encoded = base64.b64encode(pdf_bytes).decode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": encoded,
                        }
                    },
                    {
                        "text": PROMPT,
                    },
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return {
        "content": text,
        "metadata": {
            "title": title,
            "loader_strategy": "gemini_direct_pdf",
            "direct_embed_ready": True,
            "modality": "pdf",
            "url": source_ref,
        },
        "chunk_count": 1,
    }
