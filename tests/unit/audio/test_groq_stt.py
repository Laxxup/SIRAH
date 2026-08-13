from __future__ import annotations

import json

import pytest

from sirah.audio.contracts import AudioChunk
from sirah.audio.groq_stt import GroqWhisperSTT


async def test_groq_stt_uploads_wav_and_returns_transcript():
    requests: list[tuple[str, dict[str, str], bytes, float]] = []

    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        requests.append((url, headers, body, timeout))
        return json.dumps({"text": "Hola, SIRAH."}).encode()

    stt = GroqWhisperSTT.from_environment(
        environ={"SIRAH_GROQ_API_KEY": "secret"}, post=post
    )

    transcript = await stt.transcribe((AudioChunk(b"\x00\x00\xff\x7f", 16_000, 1, 10.0),))

    assert transcript.text == "Hola, SIRAH."
    assert transcript.started_at == 10.0
    assert transcript.ended_at == pytest.approx(10.000125)
    assert transcript.confidence == 1.0
    assert requests[0][0] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert requests[0][1]["Authorization"] == "Bearer secret"
    assert requests[0][1]["User-Agent"] == "SIRAH/0.3.0"
    assert b'filename="speech.wav"' in requests[0][2]
    assert b'language"\r\n\r\nes' in requests[0][2]
    assert b"RIFF" in requests[0][2]


async def test_groq_stt_requires_an_api_key():
    with pytest.raises(RuntimeError, match="SIRAH_GROQ_API_KEY"):
        GroqWhisperSTT.from_environment(environ={})


async def test_groq_stt_rejects_incompatible_audio_formats():
    stt = GroqWhisperSTT.from_environment(environ={"SIRAH_GROQ_API_KEY": "secret"})

    with pytest.raises(ValueError, match="sample rate and channels"):
        await stt.transcribe(
            (
                AudioChunk(b"\x00\x00", 16_000, 1, 1.0),
                AudioChunk(b"\x00\x00", 8_000, 1, 1.1),
            )
        )


async def test_groq_stt_rejects_non_16khz_audio() -> None:
    stt = GroqWhisperSTT.from_environment(environ={"SIRAH_GROQ_API_KEY": "secret"})

    with pytest.raises(ValueError, match="16 kHz mono"):
        await stt.transcribe((AudioChunk(b"\x00\x00", 24_000, 1, 1.0),))
