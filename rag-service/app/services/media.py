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
