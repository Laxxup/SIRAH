"""Contrato neutral y correlacionado para salida de voz."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .errors import SpeechBusyError, SpeechUnavailableError


class SpeechState(str, Enum):
    IDLE = "idle"
    SYNTHESIZING = "synthesizing"
    PLAYING = "playing"
    CANCELLING = "cancelling"
    CLOSED = "closed"


class SpeechOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class SpeechFailure(str, Enum):
    """Costura heredada para configurar fallos del fake."""

    NONE = "none"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SpeechCompletion:
    operation_id: str
    outcome: SpeechOutcome
    safe_reason: str
    finished_at: float | None


class SpeechOutputPort(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def active(self) -> bool: ...

    @property
    def state(self) -> SpeechState: ...

    def start(self, text: str) -> str: ...

    def stop(self, expected_operation_id: str | None = None) -> bool: ...

    def poll(self) -> SpeechCompletion | None: ...

    def close(self) -> None: ...


__all__ = [
    "SpeechBusyError",
    "SpeechCompletion",
    "SpeechFailure",
    "SpeechOutcome",
    "SpeechOutputPort",
    "SpeechState",
    "SpeechUnavailableError",
]
