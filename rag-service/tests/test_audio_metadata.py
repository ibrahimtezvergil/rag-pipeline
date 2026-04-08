import pytest
import sys
from types import SimpleNamespace

from app.services import audio_metadata as audio_metadata_module


@pytest.mark.asyncio
async def test_extract_audio_metadata_returns_unavailable_when_disabled(monkeypatch):
    class FakeSettings:
        audio_metadata_enabled = False

    monkeypatch.setattr(audio_metadata_module, "get_settings", lambda: FakeSettings(), raising=False)

    result = await audio_metadata_module.extract_audio_metadata(b"ID3voice", filename="voice.mp3")

    assert result == {
        "status": "unavailable",
        "provider": "disabled",
        "transcript": None,
        "segments": [],
    }


@pytest.mark.asyncio
async def test_extract_audio_metadata_defaults_to_unavailable_when_enabled(monkeypatch):
    class FakeSettings:
        audio_metadata_enabled = True

    monkeypatch.setattr(audio_metadata_module, "get_settings", lambda: FakeSettings(), raising=False)

    result = await audio_metadata_module.extract_audio_metadata(b"ID3voice", filename="voice.mp3")

    assert result == {
        "status": "unavailable",
        "provider": "whisper",
        "transcript": None,
        "segments": [],
    }


@pytest.mark.asyncio
async def test_extract_audio_metadata_normalizes_provider_segments(monkeypatch):
    class FakeSettings:
        audio_metadata_enabled = True

    async def fake_provider(_audio_bytes, *, filename=None):
        assert filename == "voice.mp3"
        return {
            "text": "Merhaba dunya",
            "segments": [
                {"start": 0.0, "end": 4.8, "text": "Merhaba dunya", "avg_logprob": -0.1}
            ],
        }

    monkeypatch.setattr(audio_metadata_module, "get_settings", lambda: FakeSettings(), raising=False)
    monkeypatch.setattr(audio_metadata_module, "_run_transcription_provider", fake_provider, raising=False)

    result = await audio_metadata_module.extract_audio_metadata(b"ID3voice", filename="voice.mp3")

    assert result["status"] == "ok"
    assert result["provider"] == "whisper"
    assert result["transcript"] == "Merhaba dunya"
    assert result["segments"] == [
        {
            "segment_index": 0,
            "start_second": 0,
            "end_second": 4,
            "text": "Merhaba dunya",
            "confidence": 0.9,
            "speaker_label": None,
        }
    ]


@pytest.mark.asyncio
async def test_extract_audio_metadata_returns_unavailable_when_provider_dependency_missing(monkeypatch):
    class FakeSettings:
        audio_metadata_enabled = True

    async def fake_provider(_audio_bytes, *, filename=None):
        raise ImportError("faster_whisper is not installed")

    monkeypatch.setattr(audio_metadata_module, "get_settings", lambda: FakeSettings(), raising=False)
    monkeypatch.setattr(audio_metadata_module, "_run_transcription_provider", fake_provider, raising=False)

    result = await audio_metadata_module.extract_audio_metadata(b"ID3voice", filename="voice.mp3")

    assert result == {
        "status": "unavailable",
        "provider": "whisper",
        "transcript": None,
        "segments": [],
    }


@pytest.mark.asyncio
async def test_run_local_whisper_transcription_uses_faster_whisper_segments(monkeypatch):
    captured = {}

    class FakeSegment:
        def __init__(self, start, end, text, avg_logprob):
            self.start = start
            self.end = end
            self.text = text
            self.avg_logprob = avg_logprob

    class FakeWhisperModel:
        def __init__(self, model_size, device, compute_type):
            captured["init"] = {
                "model_size": model_size,
                "device": device,
                "compute_type": compute_type,
            }

        def transcribe(self, file_path, word_timestamps):
            captured["file_path"] = file_path
            captured["word_timestamps"] = word_timestamps
            return (
                [
                    FakeSegment(0.0, 4.8, "Merhaba dunya", -0.1),
                    FakeSegment(5.1, 8.9, "ikinci satir", -0.3),
                ],
                SimpleNamespace(language="tr"),
            )

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    result = await audio_metadata_module._run_local_whisper_transcription(
        b"ID3voice",
        filename="voice.mp3",
    )

    assert captured["init"] == {
        "model_size": "base",
        "device": "cpu",
        "compute_type": "int8",
    }
    assert captured["word_timestamps"] is False
    assert result["text"] == "Merhaba dunya ikinci satir"
    assert result["segments"] == [
        {"start": 0.0, "end": 4.8, "text": "Merhaba dunya", "avg_logprob": -0.1},
        {"start": 5.1, "end": 8.9, "text": "ikinci satir", "avg_logprob": -0.3},
    ]
