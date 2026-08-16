"""Asynchronous PCM playback with operation-scoped cancellation."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from typing import Any

_Sink = Callable[[bytes], Awaitable[None]]
_StreamFactory = Callable[..., object]

_logger = logging.getLogger(__name__)


class PCMPlayer:
    """Deliver PCM to an injected sink, dropping audio from cancelled operations."""

    def __init__(self, sink: _Sink, *, queue_size: int = 8) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        self._sink = sink
        self._queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(queue_size)
        self._cancelled: set[str] = set()
        self._pending: dict[str, set[asyncio.Task[object]]] = {}
        self._worker: asyncio.Task[None] | None = None
        self._active_operation: str | None = None
        self._sink_task: asyncio.Future[None] | None = None

    async def play(self, operation_id: str, pcm: bytes) -> None:
        """Queue PCM unless its operation has already been cancelled."""
        self._ensure_worker()
        if operation_id in self._cancelled:
            return
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("playback requires an asyncio task")
        pending = self._pending.setdefault(operation_id, set())
        pending.add(task)
        try:
            await self._queue.put((operation_id, pcm))
        finally:
            pending.discard(task)
            if not pending:
                self._pending.pop(operation_id, None)

    async def cancel(self, operation_id: str) -> None:
        """Invalidate an operation and remove all of its pending audio."""
        self._cancelled.add(operation_id)
        current_task = asyncio.current_task()
        for task in tuple(self._pending.get(operation_id, ())):
            if task is not current_task:
                task.cancel()
        if self._active_operation == operation_id and self._sink_task is not None:
            self._sink_task.cancel()

        retained: list[tuple[str, bytes]] = []
        while True:
            try:
                queued_operation, pcm = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._queue.task_done()
            if queued_operation != operation_id:
                retained.append((queued_operation, pcm))
        for item in retained:
            self._queue.put_nowait(item)

    async def play_stream(self, operation_id: str, pcm_stream: AsyncIterator[bytes]) -> None:
        """Deliver PCM chunks in arrival order and stop if the operation is cancelled."""
        async for pcm in pcm_stream:
            if operation_id in self._cancelled:
                return
            await self.play(operation_id, pcm)
        await self.join()

    async def join(self) -> None:
        """Wait until queued PCM has either played or been discarded."""
        await self._queue.join()

    async def close(self) -> None:
        """Cancel outstanding playback and stop the worker."""
        if self._sink_task is not None:
            self._sink_task.cancel()
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def _ensure_worker(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            operation_id, pcm = await self._queue.get()
            try:
                if operation_id in self._cancelled:
                    continue
                self._active_operation = operation_id
                self._sink_task = asyncio.ensure_future(self._sink(pcm))
                try:
                    await self._sink_task
                except asyncio.CancelledError:
                    if operation_id not in self._cancelled:
                        raise
                except Exception as exc:  # noqa: BLE001 - a failing sink must not kill the worker.
                    _logger.warning("sink error while playing %s: %r", operation_id, exc)
            finally:
                self._active_operation = None
                self._sink_task = None
                self._queue.task_done()


class SoundDevicePCMPlayer:
    """Operation-aware 16 kHz mono PCM playback through sounddevice."""

    def __init__(
        self,
        *,
        device: int | str | None = None,
        sample_rate: int = 16_000,
        stream_factory: _StreamFactory | None = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._device = device
        self._sample_rate = sample_rate
        self._stream_factory = stream_factory
        self._player = PCMPlayer(self._sink)
        self._audio_owner = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sirah-audio")
        self._active_stream_operation: str | None = None
        self._cancelled_streams: set[str] = set()
        self._bluealsa_process: subprocess.Popen[bytes] | None = None
        self._owner_closed = False

    async def play(self, operation_id: str, pcm: bytes) -> None:
        await self._player.play(operation_id, pcm)

    async def cancel(self, operation_id: str) -> None:
        if self._active_stream_operation == operation_id:
            self._cancelled_streams.add(operation_id)
            if self._bluealsa_process is not None:
                await asyncio.to_thread(self._terminate_bluealsa_process, self._bluealsa_process)
            return
        await self._player.cancel(operation_id)
        await asyncio.to_thread(self._stop)

    async def join(self) -> None:
        await self._player.join()

    async def play_stream(self, operation_id: str, pcm_stream: AsyncIterator[bytes]) -> None:
        if self._device == "bluealsa":
            await self._play_bluealsa_stream(operation_id, pcm_stream)
            return
        stream = await self._owner_call(self._open_output_stream)
        self._active_stream_operation = operation_id
        interrupted = False
        try:
            async for pcm in pcm_stream:
                if operation_id in self._cancelled_streams:
                    interrupted = True
                    break
                write = asyncio.create_task(self._owner_call(stream.write, pcm))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    interrupted = True
                    await asyncio.shield(write)
                    raise
        finally:
            if operation_id in self._cancelled_streams:
                interrupted = True
            if interrupted:
                await self._owner_call(stream.abort)
            else:
                await self._owner_call(stream.stop)
            await self._owner_call(stream.close)
            self._cancelled_streams.discard(operation_id)
            if self._active_stream_operation == operation_id:
                self._active_stream_operation = None

    async def _play_bluealsa_stream(
        self, operation_id: str, pcm_stream: AsyncIterator[bytes]
    ) -> None:
        process = await asyncio.to_thread(self._open_bluealsa_process)
        self._active_stream_operation = operation_id
        self._bluealsa_process = process
        cancelled = False
        try:
            async for pcm in pcm_stream:
                if operation_id in self._cancelled_streams:
                    cancelled = True
                    break
                await asyncio.to_thread(self._write_bluealsa_pcm, process, pcm)
        finally:
            cancelled = cancelled or operation_id in self._cancelled_streams
            await asyncio.to_thread(self._finish_bluealsa_process, process, cancelled)
            self._cancelled_streams.discard(operation_id)
            if self._bluealsa_process is process:
                self._bluealsa_process = None
            if self._active_stream_operation == operation_id:
                self._active_stream_operation = None

    async def close(self) -> None:
        await self._player.close()
        if self._active_stream_operation is None:
            await asyncio.to_thread(self._stop)
        if not self._owner_closed:
            self._audio_owner.shutdown(wait=True)
            self._owner_closed = True

    async def _sink(self, pcm: bytes) -> None:
        await asyncio.to_thread(self._play, pcm)

    def _play(self, pcm: bytes) -> None:
        if self._device == "bluealsa":
            subprocess.run(
                [
                    "aplay",
                    "-D",
                    "bluealsa",
                    "-f",
                    "S16_LE",
                    "-r",
                    str(self._sample_rate),
                    "-c",
                    "1",
                    "-t",
                    "raw",
                ],
                input=pcm,
                check=True,
            )
            return
        try:
            import numpy
            import sounddevice
        except ImportError as exc:
            raise RuntimeError('install audio support: pip install -e ".[audio]"') from exc
        sounddevice.play(
            numpy.frombuffer(pcm, dtype=numpy.int16), self._sample_rate, device=self._device
        )
        sounddevice.wait()

    def _open_bluealsa_process(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._bluealsa_command(),
            stdin=subprocess.PIPE,
        )

    def _write_bluealsa_pcm(self, process: subprocess.Popen[bytes], pcm: bytes) -> None:
        if process.stdin is None:
            raise RuntimeError("BlueALSA input pipe is unavailable")
        process.stdin.write(pcm)
        process.stdin.flush()

    def _finish_bluealsa_process(self, process: subprocess.Popen[bytes], cancelled: bool) -> None:
        if cancelled:
            self._terminate_bluealsa_process(process)
        elif process.stdin is not None:
            process.stdin.close()
        returncode = process.wait()
        if returncode and not cancelled:
            raise subprocess.CalledProcessError(returncode, self._bluealsa_command())

    @staticmethod
    def _terminate_bluealsa_process(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.terminate()

    def _bluealsa_command(self) -> list[str]:
        return [
            "aplay",
            "-D",
            "bluealsa",
            "-f",
            "S16_LE",
            "-r",
            str(self._sample_rate),
            "-c",
            "1",
            "-t",
            "raw",
        ]

    def _open_output_stream(self) -> Any:
        try:
            import sounddevice
        except ImportError as exc:
            raise RuntimeError('install audio support: pip install -e ".[audio]"') from exc
        factory: Callable[..., Any] = self._stream_factory or sounddevice.RawOutputStream
        stream = factory(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            device=self._device,
            latency=0.3,
        )
        stream.start()
        return stream

    def _close_output_stream(self, stream: Any) -> None:
        stream.stop()
        stream.close()

    def _stop(self) -> None:
        try:
            import sounddevice
        except ImportError:
            return
        sounddevice.stop()

    async def _owner_call(self, function: Callable[..., Any], *args: Any) -> Any:
        if self._owner_closed:
            raise RuntimeError("audio owner has closed")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._audio_owner, function, *args)
