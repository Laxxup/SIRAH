from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from sirah.audio.tts import AsyncTTS


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.requests.append(text)
        return b"pcm"


async def test_tts_lazily_synthesizes_with_injected_provider_client():
    clients: list[FakeClient] = []

    def factory() -> FakeClient:
        client = FakeClient()
        clients.append(client)
        return client

    tts = AsyncTTS(factory)
    assert clients == []

    assert await tts.synthesize("reply-1", "hola") == b"pcm"
    assert clients[0].requests == ["hola"]


async def test_cancelling_operation_cancels_inflight_synthesis():
    started = asyncio.Event()

    class BlockingClient:
        async def synthesize(self, _text: str) -> bytes:
            started.set()
            await asyncio.Event().wait()
            return b"unreachable"

    tts = AsyncTTS(BlockingClient)
    synthesis = asyncio.create_task(tts.synthesize("reply-1", "hola"))
    await started.wait()

    await tts.cancel("reply-1")

    with pytest.raises(asyncio.CancelledError):
        await synthesis


async def test_tts_relays_provider_pcm_stream_under_its_operation_id():
    class StreamingClient:
        async def synthesize(self, _text: str) -> bytes:
            raise AssertionError("streaming provider must not synthesize a complete response")

        async def stream(self, _text: str) -> AsyncIterator[bytes]:
            yield b"first"
            yield b"last"

    tts = AsyncTTS(StreamingClient)

    assert [chunk async for chunk in tts.stream("reply-1", "hola")] == [b"first", b"last"]
