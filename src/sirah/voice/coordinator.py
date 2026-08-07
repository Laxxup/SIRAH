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
    def __init__(self, direction: AudioTurnDirection, autonomous: bool):
        self.id = str(uuid.uuid4())
        self.direction = direction
        self.autonomous = autonomous
        self.generation = 0


class AudioTurnCoordinator:
    def __init__(self) -> None:
        self._lease: _Lease | None = None
        self._lock = asyncio.Lock()
        self._available = asyncio.Condition(self._lock)
        self._generation = 0
        self._human_waiting = 0

    async def reserve(self, direction: AudioTurnDirection, *, autonomous: bool = False) -> str:
        async with self._lock:
            if self._lease is not None:
                raise AudioTurnBusyError(
                    f"turn held by {self._lease.direction.name}"
                )
            self._generation += 1
            self._lease = _Lease(direction, autonomous)
            self._lease.generation = self._generation
            return self._lease.id

    async def reserve_human_input(self) -> str:
        """Wait for autonomous output while rejecting another human operation."""
        async with self._available:
            self._human_waiting += 1
            try:
                while self._lease is not None and self._lease.autonomous:
                    await self._available.wait()
                if self._lease is not None:
                    raise AudioTurnBusyError(f"turn held by {self._lease.direction.name}")
                self._generation += 1
                self._lease = _Lease(AudioTurnDirection.INPUT, autonomous=False)
                self._lease.generation = self._generation
                return self._lease.id
            finally:
                self._human_waiting -= 1

    async def reserve_autonomous_output(self) -> str:
        """Wait until all human input has priority access to the lease."""
        async with self._available:
            while self._lease is not None or self._human_waiting:
                await self._available.wait()
            self._generation += 1
            self._lease = _Lease(AudioTurnDirection.OUTPUT, autonomous=True)
            self._lease.generation = self._generation
            return self._lease.id

    async def release(self, lease_id: str) -> None:
        async with self._available:
            if self._lease is None:
                return
            if self._lease.id != lease_id:
                return
            self._lease = None
            self._available.notify_all()

    async def transfer(self, lease_id: str, direction: AudioTurnDirection) -> bool:
        """Switch a held lease between input and output without an idle gap."""
        async with self._lock:
            if self._lease is None or self._lease.id != lease_id:
                return False
            self._lease.direction = direction
            return True

    @property
    def direction(self) -> AudioTurnDirection:
        if self._lease is None:
            return AudioTurnDirection.IDLE
        return self._lease.direction

    @property
    def is_free(self) -> bool:
        return self._lease is None
