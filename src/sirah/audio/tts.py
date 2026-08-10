"""Provider-neutral asynchronous text-to-speech boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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

    async def cancel(self, operation_id: str) -> None:
        """Cancel the in-flight synthesis task for an operation, if any."""
        task = self._active.get(operation_id)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    def _get_client(self) -> _TTSClient:
        if self._client is None:
            self._client = self._client_factory()
        return self._client
