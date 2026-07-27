"""Exclusión mutua correlacionada para turnos locales de audio."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from enum import Enum

from .errors import AudioTurnBusyError


class AudioTurnDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class AudioTurnState(str, Enum):
    IDLE = "idle"
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class AudioTurnLease:
    token: str
    direction: AudioTurnDirection
    generation: int


@dataclass(frozen=True, slots=True)
class AudioTurnSnapshot:
    state: AudioTurnState
    generation: int
    lease: AudioTurnLease | None


class AudioTurnCoordinator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._lease: AudioTurnLease | None = None

    def reserve_input(self) -> AudioTurnLease:
        return self._reserve(AudioTurnDirection.INPUT)

    def reserve_output(self) -> AudioTurnLease:
        return self._reserve(AudioTurnDirection.OUTPUT)

    def _reserve(self, direction: AudioTurnDirection) -> AudioTurnLease:
        with self._lock:
            if self._lease is not None:
                raise AudioTurnBusyError("El turno de audio está ocupado.")
            self._generation += 1
            lease = AudioTurnLease(uuid.uuid4().hex, direction, self._generation)
            self._lease = lease
            return lease

    def release(self, lease: AudioTurnLease) -> bool:
        with self._lock:
            if self._lease != lease:
                return False
            self._lease = None
            return True

    def snapshot(self) -> AudioTurnSnapshot:
        with self._lock:
            lease = self._lease
            state = (
                AudioTurnState.IDLE
                if lease is None
                else AudioTurnState(lease.direction.value)
            )
            return AudioTurnSnapshot(state, self._generation, lease)

