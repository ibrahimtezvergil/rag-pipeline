from __future__ import annotations

import httpx

from app.config import get_settings
from app.services.circuit_breaker import get_circuit_breaker
from app.services.tracing import observe, update_current_observation


@observe(name="gemini-generate", as_type="generation")
async def generate(prompt: str) -> str:
    settings = get_settings()
    if not settings.gemini_api_key.strip() or settings.gemini_api_key.strip() == "test-key":
        raise RuntimeError("Gemini text generation is not configured")
    update_current_observation(
        metadata={"provider": "gemini", "model": settings.formatter_model}
    )
    breaker = get_circuit_breaker("gemini_llm")
    breaker.before_call()
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
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        except Exception:
            breaker.record_failure()
            raise
    breaker.record_success()

    parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts).strip()
    return text[: settings.formatter_output_char_limit]
