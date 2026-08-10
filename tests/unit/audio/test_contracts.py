from __future__ import annotations

import pytest

from sirah.audio.contracts import AudioChunk, Transcript


def test_audio_chunk_keeps_pcm_format_and_monotonic_timestamp():
    chunk = AudioChunk(b"\x00\x01", sample_rate=16000, channels=1, observed_at=1.25)

    assert chunk.pcm == b"\x00\x01"
    assert chunk.sample_rate == 16000
    assert chunk.channels == 1
    assert chunk.observed_at == 1.25


def test_audio_chunk_rejects_invalid_format():
    with pytest.raises(ValueError, match="sample_rate"):
        AudioChunk(b"", sample_rate=0, channels=1, observed_at=0.0)
    with pytest.raises(ValueError, match="channels"):
        AudioChunk(b"", sample_rate=16000, channels=0, observed_at=0.0)
    with pytest.raises(TypeError, match="pcm"):
        AudioChunk("not bytes", sample_rate=16000, channels=1, observed_at=0.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="observed_at"):
        AudioChunk(b"", sample_rate=16000, channels=1, observed_at=float("nan"))


def test_transcript_requires_a_bounded_interval_and_confidence():
    transcript = Transcript("hola", started_at=1.0, ended_at=1.5, confidence=0.9)

    assert transcript.text == "hola"
    with pytest.raises(ValueError, match="ended_at"):
        Transcript("hola", started_at=2.0, ended_at=1.0, confidence=0.9)
    with pytest.raises(ValueError, match="confidence"):
        Transcript("hola", started_at=1.0, ended_at=1.5, confidence=1.1)
