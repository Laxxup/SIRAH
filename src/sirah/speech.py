"""Puerto neutral para salida de voz simulada."""
from __future__ import annotations
from enum import Enum
from typing import Protocol

class SpeechFailure(str, Enum):
    NONE = "none"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"

class SpeechOutputPort(Protocol):
    @property
    def active(self) -> bool: ...
    @property
    def available(self) -> bool: ...
    def start(self, text: str) -> None: ...
    def stop(self) -> None: ...
    def complete(self) -> None: ...
