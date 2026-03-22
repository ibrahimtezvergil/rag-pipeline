from __future__ import annotations

import httpx

from app.config import get_settings


async def generate(prompt: str) -> str:
    settings = get_settings()
    if not settings.gemini_api_key.strip() or settings.gemini_api_key.strip() == "test-key":
        raise RuntimeError("Gemini text generation is not configured")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{settings.formatter_model}:generateContent"
    )
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}],
            }
        ]
    }
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts).strip()
    return text[: settings.formatter_output_char_limit]
