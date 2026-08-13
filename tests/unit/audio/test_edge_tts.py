from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest

from sirah.audio.edge_tts import EdgeTextToSpeech


async def test_edge_tts_synthesizes_mp3_and_decodes_pcm():
    calls: list[tuple[str, str]] = []

    async def synthesize(text: str, voice: str) -> bytes:
        calls.append((text, voice))
        return b"mp3"

    def decode(mp3: bytes) -> bytes:
        assert mp3 == b"mp3"
        return b"pcm"

    tts = EdgeTextToSpeech("es-MX-DaliaNeural", synthesize=synthesize, decode=decode)

    assert await tts.synthesize("Hola") == b"pcm"
    assert calls == [("Hola", "es-MX-DaliaNeural")]


async def test_edge_tts_skips_empty_text_without_network_work():
    async def synthesize(_text: str, _voice: str) -> bytes:
        raise AssertionError("must not synthesize empty text")

    tts = EdgeTextToSpeech("es-MX-DaliaNeural", synthesize=synthesize, decode=lambda _: b"pcm")

    assert await tts.synthesize("   ") == b""


async def test_edge_tts_reports_missing_optional_dependency(monkeypatch):
    tts = EdgeTextToSpeech("es-MX-DaliaNeural")

    monkeypatch.setitem(sys.modules, "edge_tts", None)

    with pytest.raises(RuntimeError, match="edge TTS support"):
        await tts.synthesize("Hola")


async def test_edge_tts_decodes_and_yields_audio_before_the_response_finishes():
    async def encoded_audio(_text: str, _voice: str) -> AsyncIterator[bytes]:
        yield b"mp3-first"
        yield b"mp3-last"

    async def decode(encoded: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        async for chunk in encoded:
            yield chunk.replace(b"mp3", b"pcm")

    tts = EdgeTextToSpeech(
        "es-MX-DaliaNeural",
        stream=encoded_audio,
        decode_stream=decode,
    )

    assert [chunk async for chunk in tts.stream("Hola")] == [b"pcm-first", b"pcm-last"]


async def test_edge_tts_stream_waits_for_cancelled_feeder_before_stopping_ffmpeg(monkeypatch):
    stdin = Mock(drain=AsyncMock())
    stdout = AsyncMock()
    stdout.read.side_effect = [b"pcm", asyncio.CancelledError()]
    process = Mock(stdin=stdin, stdout=stdout, returncode=None, wait=AsyncMock(return_value=-9))

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr("sirah.audio.edge_tts.asyncio.create_subprocess_exec", create_process)

    async def encoded() -> AsyncIterator[bytes]:
        yield b"mp3"
        await __import__("asyncio").Event().wait()

    decoder = __import__("sirah.audio.edge_tts", fromlist=["_decode_pcm_stream"])._decode_pcm_stream
    stream = decoder(encoded())

    assert await anext(stream) == b"pcm"
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)
    await stream.aclose()

    assert process.wait.await_count == 1


async def test_edge_tts_stops_ffmpeg_when_the_encoded_stream_fails(monkeypatch):
    stdin = Mock(drain=AsyncMock())
    stdout = AsyncMock()
    process = Mock(stdin=stdin, stdout=stdout, returncode=None, wait=AsyncMock(return_value=-9))

    async def create_process(*_args, **_kwargs):
        return process

    monkeypatch.setattr("sirah.audio.edge_tts.asyncio.create_subprocess_exec", create_process)

    async def encoded() -> AsyncIterator[bytes]:
        raise RuntimeError("Edge failed")
        yield b"unreachable"

    decoder = __import__("sirah.audio.edge_tts", fromlist=["_decode_pcm_stream"])._decode_pcm_stream

    with pytest.raises(RuntimeError, match="Edge failed"):
        await anext(decoder(encoded()))

    process.kill.assert_called_once()
    assert process.wait.await_count == 1
