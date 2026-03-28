import pytest

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
