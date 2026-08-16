"""Provider-neutral asynchronous text-to-speech boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Protocol


class _TTSClient(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


_ClientFactory = Callable[[], _TTSClient]


class AsyncTTS:
    """Lazily create an injected provider client and track synthesis by operation."""

    def __init__(self, client_factory: _ClientFactory) -> None:
        self._client_factory = client_factory
        self._client: _TTSClient | None = None
        self._active: dict[str, asyncio.Task[object]] = {}

    async def synthesize(self, operation_id: str, text: str) -> bytes:
        """Synthesize text through the configured provider client."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("synthesis requires an asyncio task")
        self._active[operation_id] = task
        try:
            return await self._get_client().synthesize(text)
        finally:
            if self._active.get(operation_id) is task:
                self._active.pop(operation_id, None)

    async def stream(self, operation_id: str, text: str) -> AsyncIterator[bytes]:
        """Yield provider PCM incrementally when its adapter supports streaming."""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("synthesis requires an asyncio task")
        self._active[operation_id] = task
        try:
            stream = getattr(self._get_client(), "stream", None)
            if stream is None:
                yield await self._get_client().synthesize(text)
                return
            async for pcm in stream(text):
                yield pcm
        finally:
            if self._active.get(operation_id) is task:
                self._active.pop(operation_id, None)

    async def cancel(self, operation_id: str) -> None:
        """Cancel the in-flight synthesis task for an operation, if any."""
        task = self._active.get(operation_id)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _get_client(self) -> _TTSClient:
        if self._client is None:
            self._client = self._client_factory()
        return self._client


class FallbackTTS:
    """Compose a primary provider with a fallback used when it fails.

    Satisfies the same `OperationTTS` contract as `AsyncTTS`: synthesis
    failures on the primary fall through to the fallback, cancellation is
    forwarded to both, and streaming is preserved when the primary (or
    fallback) exposes a `stream` method.
    """

    def __init__(
        self,
        primary: _ClientFactory,
        fallback: _ClientFactory,
        on_fallback: Callable[[Exception], None] | None = None,
    ) -> None:
        self._primary = AsyncTTS(primary)
        self._fallback = AsyncTTS(fallback)
        self._on_fallback = on_fallback
        self._fallback_used = False

    @property
    def fallback_used(self) -> bool:
        return self._fallback_used

    async def synthesize(self, operation_id: str, text: str) -> bytes:
        try:
            return await self._primary.synthesize(operation_id, text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fall back on any provider failure.
            self._fallback_used = True
            if self._on_fallback is not None:
                self._on_fallback(exc)
            return await self._fallback.synthesize(operation_id, text)

    async def stream(self, operation_id: str, text: str) -> AsyncIterator[bytes]:
        primary_stream = getattr(self._primary, "stream", None)
        try:
            if primary_stream is None:
                yield await self._primary.synthesize(operation_id, text)
                return
            async for pcm in primary_stream(operation_id, text):
                yield pcm
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - fall back on any provider failure.
            self._fallback_used = True
            if self._on_fallback is not None:
                self._on_fallback(exc)
        fallback_stream = getattr(self._fallback, "stream", None)
        if fallback_stream is not None:
            async for pcm in fallback_stream(operation_id, text):
                yield pcm
            return
        yield await self._fallback.synthesize(operation_id, text)

    async def cancel(self, operation_id: str) -> None:
        await self._primary.cancel(operation_id)
        await self._fallback.cancel(operation_id)
