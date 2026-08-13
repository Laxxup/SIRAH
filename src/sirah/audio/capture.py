"""SoundDevice-backed audio capture with an asyncio-facing queue."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from sirah.audio.contracts import AudioChunk

_StreamFactory = Callable[..., object]


class SoundDeviceAudioSource:
    """Capture PCM blocks without blocking consumers of the asyncio loop."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        channels: int = 1,
        blocksize: int = 0,
        queue_size: int = 8,
        device: int | str | None = None,
        stream_factory: _StreamFactory | None = None,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self._sample_rate = sample_rate
        self._channels = channels
        self._blocksize = blocksize
        self._queue: asyncio.Queue[AudioChunk] = asyncio.Queue(maxsize=queue_size)
        self._device = device
        self._stream_factory = stream_factory
        self._stream: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dropped_chunks = 0
        self._queue_high_water_mark = 0

    @property
    def dropped_chunks(self) -> int:
        return self._dropped_chunks

    @property
    def queue_high_water_mark(self) -> int:
        return self._queue_high_water_mark

    async def start(self) -> None:
        if self._stream is not None:
            return
        self._loop = asyncio.get_running_loop()
        factory = self._stream_factory or _sounddevice_input_stream
        self._stream = factory(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._blocksize,
            device=self._device,
            callback=self._on_audio,
        )
        self._stream.start()  # type: ignore[attr-defined]

    async def next_chunk(self) -> AudioChunk:
        if self._stream is None:
            raise RuntimeError("audio source has not started")
        return await self._queue.get()

    async def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()  # type: ignore[attr-defined]
        self._stream.close()  # type: ignore[attr-defined]
        self._stream = None
        self._loop = None

    def _on_audio(
        self, indata: Any, _frames: int, time_info: Any, _status: Any
    ) -> None:
        if self._loop is None:
            return
        observed_at = (
            time_info["inputBufferAdcTime"]
            if isinstance(time_info, dict)
            else time_info.inputBufferAdcTime
        )
        pcm = indata if isinstance(indata, bytes) else indata.tobytes()
        chunk = AudioChunk(pcm, self._sample_rate, self._channels, observed_at)
        self._loop.call_soon_threadsafe(self._enqueue, chunk)

    def _enqueue(self, chunk: AudioChunk) -> None:
        if self._queue.full():
            self._queue.get_nowait()
            self._dropped_chunks += 1
        self._queue.put_nowait(chunk)
        self._queue_high_water_mark = max(self._queue_high_water_mark, self._queue.qsize())


def _sounddevice_input_stream(**kwargs: Any) -> object:
    try:
        import sounddevice
    except ImportError as exc:
        raise RuntimeError('install audio support: pip install -e ".[audio]"') from exc
    return sounddevice.InputStream(**kwargs)
