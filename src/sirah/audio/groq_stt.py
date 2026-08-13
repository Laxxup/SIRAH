"""Groq-hosted Whisper speech-to-text adapter."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
import wave
from collections.abc import Awaitable, Callable, Mapping, Sequence
from io import BytesIO

from sirah.audio.contracts import AudioChunk, Transcript

HttpPost = Callable[[str, dict[str, str], bytes, float], Awaitable[bytes]]

_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_BOUNDARY = "sirah-groq-whisper"


class GroqWhisperSTT:
    """Upload a completed PCM turn to Groq Whisper as a WAV file."""

    def __init__(self, api_key: str, *, post: HttpPost, timeout_s: float = 15.0) -> None:
        self._api_key = api_key
        self._post = post
        self._timeout_s = timeout_s

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        post: HttpPost | None = None,
    ) -> GroqWhisperSTT:
        values = os.environ if environ is None else environ
        api_key = values.get("SIRAH_GROQ_API_KEY", "")
        if not api_key:
            raise RuntimeError("SIRAH_GROQ_API_KEY is required for Groq STT")
        return cls(api_key, post=post or _post)

    async def transcribe(self, chunks: Sequence[AudioChunk]) -> Transcript:
        if not chunks:
            raise ValueError("at least one audio chunk is required")
        first = chunks[0]
        if any(
            chunk.sample_rate != first.sample_rate or chunk.channels != first.channels
            for chunk in chunks[1:]
        ):
            raise ValueError("all chunks must use the same sample rate and channels")
        if first.sample_rate != 16_000 or first.channels != 1:
            raise ValueError("Groq STT requires 16 kHz mono audio")
        pcm = b"".join(chunk.pcm for chunk in chunks)
        response = await self._post(
            _URL,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": f"multipart/form-data; boundary={_BOUNDARY}",
                "User-Agent": "SIRAH/0.3.0",
            },
            _multipart_body(_wav(pcm, first.sample_rate, first.channels)),
            self._timeout_s,
        )
        try:
            text = json.loads(response)["text"]
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Groq STT returned an invalid response") from exc
        if not isinstance(text, str):
            raise TypeError("Groq STT returned an invalid transcript")
        duration = len(pcm) / (first.sample_rate * first.channels * 2)
        return Transcript(text.strip(), first.observed_at, first.observed_at + duration, 1.0)


def _wav(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm)
    return buffer.getvalue()


def _multipart_body(wav: bytes) -> bytes:
    parts = (
        ("model", "whisper-large-v3-turbo"),
        ("language", "es"),
        ("response_format", "json"),
    )
    body = bytearray()
    for name, value in parts:
        body.extend(f"--{_BOUNDARY}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f"--{_BOUNDARY}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n')
    body.extend(b"Content-Type: audio/wav\r\n\r\n")
    body.extend(wav)
    body.extend(f"\r\n--{_BOUNDARY}--\r\n".encode())
    return bytes(body)


async def _post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
    def send() -> bytes:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    return await asyncio.to_thread(send)
