from app.services import media as media_module


def test_probe_audio_duration_seconds_uses_ffprobe_output(monkeypatch):
    monkeypatch.setattr(media_module, "_probe_media_duration_with_ffprobe", lambda *_args, **_kwargs: 255.4)

    assert media_module.probe_audio_duration_seconds(b"ID3voice", "voice.mp3") == 255


def test_slice_audio_clip_bytes_returns_distinct_ranges(monkeypatch):
    calls = []

    def fake_slice(binary, filename, start_second, end_second):
        calls.append((binary, filename, start_second, end_second))
        return f"{start_second}-{end_second}".encode()

    monkeypatch.setattr(media_module, "_slice_audio_with_ffmpeg", fake_slice)

    clips = media_module.slice_audio_clip_bytes(
        b"ID3voice",
        "voice.mp3",
        [
            {"clip_index": 0, "start_second": 0, "end_second": 120},
            {"clip_index": 1, "start_second": 120, "end_second": 240},
        ],
    )

    assert [clip["audio_bytes"] for clip in clips] == [b"0-120", b"120-240"]
    assert calls == [
        (b"ID3voice", "voice.mp3", 0, 120),
        (b"ID3voice", "voice.mp3", 120, 240),
    ]
