"""Simulated voice — fake doubles for testing."""

from __future__ import annotations

import uuid
from time import monotonic

from sirah.types import SpeechCompletion, SpeechRecognitionEvent

__all__ = ["FakeSpeechInput", "FakeSpeechOutput"]


class FakeSpeechInput:
    def __init__(
        self,
        scripted: list[SpeechRecognitionEvent] | None = None,
        fail_after: int | None = None,
    ) -> None:
        self._scripted = scripted or []
        self._index = 0
        self._fail_after = fail_after
        self._call_count = 0
        self._running = False
        self._history: list[SpeechRecognitionEvent] = []

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def health(self) -> bool:
        return self._running

    async def listen(self, timeout: float | None = None) -> SpeechRecognitionEvent:
        self._call_count += 1

        if self._fail_after is not None and self._call_count > self._fail_after:
            from sirah.errors import SpeechInputError
            raise SpeechInputError("simulated failure")

        if self._index < len(self._scripted):
            event = self._scripted[self._index]
            self._index += 1
        else:
            event = SpeechRecognitionEvent(
                text="", is_final=False, confidence=0.0, timestamp=monotonic()
            )

        self._history.append(event)
        return event

    def reset(self) -> None:
        self._index = 0
        self._call_count = 0
        self._history.clear()

    @property
    def history(self) -> list[SpeechRecognitionEvent]:
        return self._history


class FakeSpeechOutput:
    def __init__(
        self,
        fail_after: int | None = None,
        delay_ms: float = 10.0,
    ) -> None:
        self._fail_after = fail_after
        self._delay_ms = delay_ms
        self._call_count = 0
        self._spoken: list[str] = []

    async def health(self) -> bool:
        return True

    async def speak(self, text: str) -> SpeechCompletion:
        import asyncio

        self._call_count += 1

        if self._fail_after is not None and self._call_count > self._fail_after:
            from sirah.errors import SpeechError
            raise SpeechError("simulated failure")

        await asyncio.sleep(self._delay_ms / 1000)
        self._spoken.append(text)

        return SpeechCompletion(
            operation_id=str(uuid.uuid4())[:8],
            success=True,
            duration_ms=self._delay_ms,
        )

    async def stop(self) -> None:
        pass

    @property
    def spoken(self) -> list[str]:
        return self._spoken

    def reset(self) -> None:
        self._call_count = 0
        self._spoken.clear()
