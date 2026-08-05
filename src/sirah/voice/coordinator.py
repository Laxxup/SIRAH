"""AudioTurnCoordinator — async lease-based semiduplex audio."""

from __future__ import annotations

import asyncio
import uuid
from enum import Enum, auto

from sirah.errors import AudioTurnBusyError

__all__ = ["AudioTurnCoordinator", "AudioTurnDirection", "AudioTurnState"]


class AudioTurnDirection(Enum):
    INPUT = auto()
    OUTPUT = auto()
    IDLE = auto()


class AudioTurnState(Enum):
    FREE = auto()
    RESERVED = auto()


class _Lease:
    def __init__(self, direction: AudioTurnDirection):
        self.id = str(uuid.uuid4())
        self.direction = direction
        self.generation = 0


class AudioTurnCoordinator:
    def __init__(self) -> None:
        self._lease: _Lease | None = None
        self._lock = asyncio.Lock()
        self._generation = 0

    async def reserve(self, direction: AudioTurnDirection) -> str:
        async with self._lock:
            if self._lease is not None:
                raise AudioTurnBusyError(
                    f"turn held by {self._lease.direction.name}"
                )
            self._generation += 1
            self._lease = _Lease(direction)
            self._lease.generation = self._generation
            return self._lease.id

    async def release(self, lease_id: str) -> None:
        async with self._lock:
            if self._lease is None:
                return
            if self._lease.id != lease_id:
                return
            self._lease = None

    @property
    def direction(self) -> AudioTurnDirection:
        if self._lease is None:
            return AudioTurnDirection.IDLE
        return self._lease.direction

    @property
    def is_free(self) -> bool:
        return self._lease is None
