from __future__ import annotations

from pathlib import Path

import httpx


async def load_binary_source(
    source_ref: str | None = None,
    *,
    source_bytes: bytes | None = None,
) -> bytes:
    if source_bytes is not None:
        return source_bytes

    assert source_ref is not None
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(source_ref)
        response.raise_for_status()
    return response.content


def detect_image_mime_type(binary: bytes, filename: str | None = None) -> str:
    if binary.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if binary.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    suffix = Path(filename or "").suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"

    raise ValueError("Unsupported image format")


def detect_audio_mime_type(binary: bytes, filename: str | None = None) -> str:
    if binary.startswith(b"ID3") or binary[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if binary.startswith(b"RIFF") and b"WAVE" in binary[:16]:
        return "audio/wav"

    suffix = Path(filename or "").suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".wav":
        return "audio/wav"

    raise ValueError("Unsupported audio format")


def probe_audio_duration_seconds(binary: bytes, filename: str | None = None) -> int:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".wav" and len(binary) >= 44:
        byte_rate = int.from_bytes(binary[28:32], "little") or 1
        data_size = max(0, len(binary) - 44)
        return max(1, data_size // byte_rate)
    return 1


def build_clip_ranges(duration_seconds: int, *, clip_seconds: int = 120) -> list[dict[str, int]]:
    normalized_duration = max(1, int(duration_seconds))
    clips: list[dict[str, int]] = []
    clip_index = 0
    for start_second in range(0, normalized_duration, clip_seconds):
        end_second = min(start_second + clip_seconds, normalized_duration)
        clips.append(
            {
                "clip_index": clip_index,
                "start_second": start_second,
                "end_second": end_second,
            }
        )
        clip_index += 1
    return clips
