"""Barge-in coordination for active synthesized responses."""

from __future__ import annotations

import asyncio
from typing import Protocol


class _Cancellable(Protocol):
    async def cancel(self, operation_id: str) -> None: ...


class BargeInController:
    """Invalidate an active response before cancelling its audio work."""

    def __init__(self, player: _Cancellable, tts: _Cancellable) -> None:
        self._player = player
        self._tts = tts
        self._active_operation: str | None = None

    def activate(self, operation_id: str) -> None:
        self._active_operation = operation_id

    def is_active(self, operation_id: str) -> bool:
        return self._active_operation == operation_id

    async def interrupt(self) -> str | None:
        """Invalidate the active operation and safely request audio cancellation."""
        operation_id = self._active_operation
        self._active_operation = None
        if operation_id is None:
            return None
        await asyncio.gather(
            self._player.cancel(operation_id),
            self._tts.cancel(operation_id),
            return_exceptions=True,
        )
        return operation_id
