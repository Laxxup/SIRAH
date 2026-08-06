"""Voice ports — async contracts for STT and TTS."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sirah.types import SpeechCompletion, SpeechRecognitionEvent

__all__ = ["SpeechInputPort", "SpeechOutputPort"]


@runtime_checkable
class SpeechOutputPort(Protocol):
    async def speak(self, text: str) -> SpeechCompletion: ...

    async def stop(self) -> None: ...

    async def health(self) -> bool: ...


@runtime_checkable
class SpeechInputPort(Protocol):
    async def listen(self, timeout: float | None = None) -> SpeechRecognitionEvent: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def health(self) -> bool: ...
