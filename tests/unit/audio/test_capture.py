from __future__ import annotations

import asyncio

from sirah.audio.capture import SoundDeviceAudioSource
from sirah.audio.contracts import AudioChunk


class FakeStream:
    def __init__(self, **kwargs: object) -> None:
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


async def test_capture_enqueues_pcm_from_injected_stream():
    created: list[FakeStream] = []

    def stream_factory(**kwargs: object) -> FakeStream:
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    source = SoundDeviceAudioSource(
        sample_rate=16_000,
        channels=1,
        stream_factory=stream_factory,
    )

    await source.start()
    created[0].callback(b"pcm", 3, {"inputBufferAdcTime": 2.5}, None)
    await asyncio.sleep(0)

    assert await source.next_chunk() == AudioChunk(b"pcm", 16_000, 1, 2.5)
    await source.stop()
    assert created[0].started
    assert created[0].stopped
    assert created[0].closed


async def test_capture_discards_oldest_chunk_when_queue_is_full():
    created: list[FakeStream] = []

    def stream_factory(**kwargs: object) -> FakeStream:
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    source = SoundDeviceAudioSource(stream_factory=stream_factory, queue_size=1)
    await source.start()

    created[0].callback(b"old", 3, {"inputBufferAdcTime": 1.0}, None)
    await asyncio.sleep(0)
    created[0].callback(b"new", 3, {"inputBufferAdcTime": 2.0}, None)
    await asyncio.sleep(0)

    assert (await source.next_chunk()).pcm == b"new"


async def test_capture_passes_the_requested_fixed_block_size_to_the_stream():
    created: list[dict[str, object]] = []

    def stream_factory(**kwargs: object) -> FakeStream:
        created.append(kwargs)
        return FakeStream(**kwargs)

    source = SoundDeviceAudioSource(blocksize=512, stream_factory=stream_factory)

    await source.start()

    assert created[0]["blocksize"] == 512
