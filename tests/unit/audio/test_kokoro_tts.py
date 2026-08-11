from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sirah.audio.kokoro_tts import KokoroTextToSpeech
from sirah.audio.tts import AsyncTTS


class FakePipeline:
    def __init__(self, audio: object) -> None:
        self.audio = audio
        self.calls: list[tuple[str, str]] = []

    def __call__(self, text: str, *, voice: str):
        self.calls.append((text, voice))
        return iter(((text, "phonemes", self.audio),))


async def test_kokoro_synthesizes_24khz_pcm_and_loads_once():
    loaded = 0
    pipeline = FakePipeline([0.0, 1.0, -1.0])

    def factory() -> FakePipeline:
        nonlocal loaded
        loaded += 1
        return pipeline

    tts = KokoroTextToSpeech("hexgrad/Kokoro-82M", "ef_dora", Path("/cache"), factory)

    assert await tts.synthesize("Hola") == b"\x00\x00\xff\x7f\x00\x80"
    assert await tts.synthesize("SIRAH") == b"\x00\x00\xff\x7f\x00\x80"
    assert tts.sample_rate == 24_000
    assert loaded == 1
    assert pipeline.calls == [("Hola", "ef_dora"), ("SIRAH", "ef_dora")]


async def test_kokoro_rejects_a_missing_model_before_synthesis():
    def factory() -> FakePipeline:
        raise FileNotFoundError("Kokoro model unavailable in /cache")

    tts = KokoroTextToSpeech("hexgrad/Kokoro-82M", "ef_dora", Path("/cache"), factory)

    with pytest.raises(RuntimeError, match="Kokoro model unavailable"):
        await tts.synthesize("Hola")


async def test_async_tts_cancellation_discards_a_blocked_local_synthesis():
    started = asyncio.Event()

    class BlockingClient:
        async def synthesize(self, _text: str) -> bytes:
            started.set()
            await asyncio.Event().wait()

    tts = AsyncTTS(lambda: BlockingClient())
    task = asyncio.create_task(tts.synthesize("local-1", "Hola"))
    await started.wait()

    await tts.cancel("local-1")

    with pytest.raises(asyncio.CancelledError):
        await task
