"""Asynchronous PCM playback with operation-scoped cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

_Sink = Callable[[bytes], Awaitable[None]]


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
            finally:
                self._active_operation = None
                self._sink_task = None
                self._queue.task_done()
