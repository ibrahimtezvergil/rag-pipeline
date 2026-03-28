from __future__ import annotations

from app.config import get_settings


async def extract_audio_metadata(
    audio_bytes: bytes,
    *,
    filename: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.audio_metadata_enabled:
        return {
            "status": "unavailable",
            "provider": "disabled",
            "transcript": None,
            "segments": [],
        }

    return {
        "status": "unavailable",
        "provider": "whisper",
        "transcript": None,
        "segments": [],
    }
