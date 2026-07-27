"""Dobles deterministas de entrada; no usan hardware ni red."""

from __future__ import annotations

from collections import deque

from .errors import SpeechInputError
from .speech_input import (
    PcmReadKind,
    PcmReadResult,
    RecognitionUpdate,
    RecognitionUpdateKind,
)


class FakePcmCapture:
    def __init__(
        self,
        results: tuple[PcmReadResult, ...] = (),
        *,
        available: bool = True,
    ) -> None:
        self.available = available
        self.safe_reason = None if available else "fake_capture_unavailable"
        self.active = False
        self.closed = False
        self.results = deque(results)

    def start(self) -> None:
        if self.closed or not self.available:
            raise SpeechInputError("fake_capture_unavailable")
        if self.active:
            raise SpeechInputError("fake_capture_busy")
        self.active = True

    def read_chunk(self) -> PcmReadResult:
        if not self.active:
            return PcmReadResult(PcmReadKind.FAILED, safe_reason="capture_not_active")
        return (
            self.results.popleft()
            if self.results
            else PcmReadResult(PcmReadKind.TIMEOUT)
        )

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.stop()
        self.closed = True
        self.available = False


class FakeSpeechRecognizer:
    def __init__(
        self,
        updates: tuple[RecognitionUpdate | None, ...] = (),
        *,
        final: RecognitionUpdate | None = None,
        available: bool = True,
    ) -> None:
        self.available = available
        self.updates = deque(updates)
        self.final = final or RecognitionUpdate(RecognitionUpdateKind.NO_SPEECH)
        self.ready = False
        self.closed = False
        self._cached: RecognitionUpdate | None = None

    def reset(self) -> None:
        if self.closed or not self.available:
            raise SpeechInputError("fake_recognizer_unavailable")
        self.ready = True
        self._cached = None

    def accept_pcm(self, chunk: bytes) -> RecognitionUpdate | None:
        if not self.ready or self._cached is not None:
            raise SpeechInputError("fake_recognizer_lifecycle_invalid")
        return self.updates.popleft() if self.updates else None

    def finalize(self) -> RecognitionUpdate:
        if not self.ready:
            raise SpeechInputError("fake_recognizer_lifecycle_invalid")
        if self._cached is None:
            self._cached = self.final
        return self._cached

    def close(self) -> None:
        self.closed = True
        self.available = False
