from __future__ import annotations

import os
import subprocess
import tempfile
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
    duration = _probe_media_duration_with_ffprobe(binary, filename)
    if duration is not None:
        return max(1, int(duration))
    return _legacy_duration_fallback(binary, filename)


def _legacy_duration_fallback(binary: bytes, filename: str | None = None) -> int:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".wav" and len(binary) >= 44:
        byte_rate = int.from_bytes(binary[28:32], "little") or 1
        data_size = max(0, len(binary) - 44)
        return max(1, data_size // byte_rate)
    return 1


def _probe_media_duration_with_ffprobe(binary: bytes, filename: str | None = None) -> float | None:
    temp_path = _write_temp_media_file(binary, filename)
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    finally:
        _remove_file_quietly(temp_path)

    if result.returncode != 0:
        return None

    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


class AudioClipSlicingError(RuntimeError):
    pass


def slice_audio_clip_bytes(
    binary: bytes,
    filename: str | None,
    clips: list[dict[str, int]],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for clip in clips:
        output.append(
            {
                **clip,
                "audio_bytes": _slice_audio_with_ffmpeg(
                    binary,
                    filename,
                    int(clip["start_second"]),
                    int(clip["end_second"]),
                ),
            }
        )
    return output


def _slice_audio_with_ffmpeg(
    binary: bytes,
    filename: str | None,
    start_second: int,
    end_second: int,
) -> bytes:
    input_path = _write_temp_media_file(binary, filename)
    suffix = Path(filename or "").suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as output_file:
        output_path = output_file.name

    try:
        copy_result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(start_second),
                "-to",
                str(end_second),
                "-i",
                input_path,
                "-c",
                "copy",
                output_path,
            ],
            check=False,
            capture_output=True,
        )
        if copy_result.returncode != 0:
            transcode_args = _ffmpeg_transcode_args_for_suffix(suffix)
            transcode_result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    str(start_second),
                    "-to",
                    str(end_second),
                    "-i",
                    input_path,
                    *transcode_args,
                    output_path,
                ],
                check=False,
                capture_output=True,
            )
            if transcode_result.returncode != 0:
                raise AudioClipSlicingError("ffmpeg failed to slice audio clip")

        with open(output_path, "rb") as clipped_file:
            return clipped_file.read()
    except FileNotFoundError as exc:
        raise AudioClipSlicingError("ffmpeg is not installed") from exc
    finally:
        _remove_file_quietly(input_path)
        _remove_file_quietly(output_path)


def _write_temp_media_file(binary: bytes, filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(binary)
        return temp_file.name


def _ffmpeg_transcode_args_for_suffix(suffix: str) -> list[str]:
    if suffix == ".wav":
        return ["-c:a", "pcm_s16le"]
    return ["-c:a", "libmp3lame"]


def _remove_file_quietly(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        return


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
