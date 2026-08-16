from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from sirah.audio.tts import AsyncTTS, FallbackTTS


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


class FailingClient:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.requests: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.requests.append(text)
        raise self.exc


async def test_fallback_tts_uses_fallback_when_primary_synthesis_fails():
    failures: list[Exception] = []

    def on_fallback(exc: Exception) -> None:
        failures.append(exc)

    tts = FallbackTTS(
        lambda: FailingClient(RuntimeError("primary down")),
        lambda: FakeClient(),
        on_fallback=on_fallback,
    )

    assert await tts.synthesize("reply-1", "hola") == b"pcm"
    assert tts.fallback_used
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)


async def test_fallback_tts_does_not_touch_fallback_when_primary_works():
    primary = FakeClient()
    tts = FallbackTTS(lambda: primary, lambda: FakeClient())

    assert await tts.synthesize("reply-1", "hola") == b"pcm"
    assert not tts.fallback_used
    assert primary.requests == ["hola"]


async def test_fallback_tts_relays_stream_fallback_for_streaming_primary():
    class FailingStreamClient:
        async def stream(self, _text: str) -> AsyncIterator[bytes]:
            yield b"first"
            raise RuntimeError("stream died")

    tts = FallbackTTS(lambda: FailingStreamClient(), lambda: FakeClient())

    assert [chunk async for chunk in tts.stream("reply-1", "hola")] == [b"first", b"pcm"]
    assert tts.fallback_used


async def test_fallback_tts_cancels_both_primary_and_fallback():
    started = asyncio.Event()

    class BlockingClient:
        async def synthesize(self, _text: str) -> bytes:
            started.set()
            await asyncio.Event().wait()
            return b"unreachable"

    tts = FallbackTTS(lambda: BlockingClient(), lambda: BlockingClient())
    synthesis = asyncio.create_task(tts.synthesize("reply-1", "hola"))
    await started.wait()

    await tts.cancel("reply-1")

    with pytest.raises(asyncio.CancelledError):
        await synthesis
