from __future__ import annotations

import os
import tempfile

from app.config import get_settings


async def extract_audio_metadata(
    audio_bytes: bytes,
    *,
    filename: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    if not settings.audio_metadata_enabled:
        return _unavailable_audio_metadata(provider="disabled")

    try:
        provider_result = await _run_transcription_provider(audio_bytes, filename=filename)
    except ImportError:
        return _unavailable_audio_metadata()

    return _normalize_audio_metadata(provider_result)


async def _run_transcription_provider(
    audio_bytes: bytes,
    *,
    filename: str | None = None,
) -> dict[str, object]:
    return await _run_local_whisper_transcription(audio_bytes, filename=filename)


async def _run_local_whisper_transcription(
    audio_bytes: bytes,
    *,
    filename: str | None = None,
) -> dict[str, object]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise ImportError("faster_whisper is not installed") from exc

    suffix = os.path.splitext(filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(audio_bytes)
        temp_path = temp_file.name

    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(temp_path, word_timestamps=False)
        normalized_segments = []
        transcript_parts = []
        for segment in segments:
            text = str(getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            transcript_parts.append(text)
            normalized_segments.append(
                {
                    "start": float(getattr(segment, "start", 0.0) or 0.0),
                    "end": float(getattr(segment, "end", 0.0) or 0.0),
                    "text": text,
                    "avg_logprob": float(getattr(segment, "avg_logprob", 0.0) or 0.0),
                }
            )
        return {
            "text": " ".join(transcript_parts).strip(),
            "segments": normalized_segments,
        }
    finally:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass


def _normalize_audio_metadata(provider_result: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(provider_result, dict):
        return _unavailable_audio_metadata()

    transcript = str(provider_result.get("text") or "").strip() or None
    normalized_segments: list[dict[str, object]] = []
    for index, segment in enumerate(provider_result.get("segments") or []):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start_second = max(0, int(float(segment.get("start") or segment.get("start_second") or 0)))
        end_second = max(start_second, int(float(segment.get("end") or segment.get("end_second") or start_second)))
        avg_logprob = segment.get("avg_logprob")
        confidence = 0.0
        if avg_logprob is not None:
            confidence = max(0.0, min(1.0, 1.0 + float(avg_logprob)))
        normalized_segments.append(
            {
                "segment_index": index,
                "start_second": start_second,
                "end_second": end_second,
                "text": text,
                "confidence": confidence,
                "speaker_label": segment.get("speaker_label"),
            }
        )

    if transcript is None and normalized_segments:
        transcript = " ".join(str(segment["text"]) for segment in normalized_segments)
    if transcript is None:
        return _unavailable_audio_metadata()

    return {
        "status": "ok",
        "provider": "whisper",
        "transcript": transcript,
        "segments": normalized_segments,
    }


def _unavailable_audio_metadata(*, provider: str = "whisper") -> dict[str, object]:
    return {
        "status": "unavailable",
        "provider": provider,
        "transcript": None,
        "segments": [],
    }
