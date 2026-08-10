"""Dependency-free audio boundaries for future push-to-talk integration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AudioChunk:
    pcm: bytes
    sample_rate: int
    channels: int
    observed_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.pcm, bytes):
            raise TypeError("pcm must be bytes")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")
        if not isfinite(self.observed_at):
            raise ValueError("observed_at must be finite")


@dataclass(frozen=True)
class Transcript:
    text: str
    started_at: float
    ended_at: float
    confidence: float

    def __post_init__(self) -> None:
        if not isfinite(self.started_at) or not isfinite(self.ended_at):
            raise ValueError("transcript timestamps must be finite")
        if self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")


@runtime_checkable
class AudioSource(Protocol):
    async def start(self) -> None: ...

    async def next_chunk(self) -> AudioChunk | None: ...

    async def stop(self) -> None: ...


@runtime_checkable
class SpeechToText(Protocol):
    async def transcribe(self, chunks: Sequence[AudioChunk]) -> Transcript: ...


@runtime_checkable
class TextToSpeech(Protocol):
    async def speak(self, text: str) -> None: ...
