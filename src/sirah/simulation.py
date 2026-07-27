"""Adaptadores simulados del circuito situacional."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from time import monotonic
from collections.abc import Callable

from sirah_cortex import Event, EventType
from sirah_cortex.domain.world_state import KnowledgeKind

from .errors import SpeechBusyError, SpeechUnavailableError
from .speech import SpeechCompletion, SpeechFailure, SpeechOutcome, SpeechState


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds no puede ser negativo.")
        self.value += seconds


class MonotonicClock:
    def now(self) -> float:
        return monotonic()


@dataclass(slots=True)
class FakeSpeechOutput:
    """Fake síncrono: no usa audio, threads ni tiempo real."""

    available: bool = True
    failure: SpeechFailure = SpeechFailure.NONE
    spoken_texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    _state: SpeechState = SpeechState.IDLE
    _operation_id: str | None = None
    _completion: SpeechCompletion | None = None
    _ids: count = field(default_factory=lambda: count(1), repr=False)
    _on_operation_accepted: Callable[[str], None] = field(
        default=lambda _operation_id: None, repr=False
    )
    _on_terminal: Callable[[str], None] = field(
        default=lambda _operation_id: None, repr=False
    )

    def set_lifecycle_hooks(
        self,
        on_operation_accepted: Callable[[str], None],
        on_terminal: Callable[[str], None],
    ) -> None:
        if self.active:
            raise SpeechBusyError("No se pueden cambiar hooks con TTS activo.")
        self._on_operation_accepted = on_operation_accepted
        self._on_terminal = on_terminal

    @property
    def state(self) -> SpeechState:
        return self._state

    @property
    def active(self) -> bool:
        return self._operation_id is not None

    def start(self, text: str) -> str:
        if (
            not self.available
            or self.failure is SpeechFailure.UNAVAILABLE
            or self._state is SpeechState.CLOSED
        ):
            self.errors.append("tts_unavailable")
            raise SpeechUnavailableError("TTS no disponible.")
        if self.failure is SpeechFailure.FAILED:
            self.errors.append("tts_failed")
            raise SpeechUnavailableError("TTS simulado falló.")
        if self.active or self._completion is not None:
            raise SpeechBusyError("TTS ya está activo.")
        operation_id = f"fake-speech-{next(self._ids)}"
        self._operation_id = operation_id
        self._state = SpeechState.PLAYING
        try:
            self._on_operation_accepted(operation_id)
        except Exception:
            self._operation_id = None
            self._state = SpeechState.IDLE
            raise
        self.spoken_texts.append(text)
        return operation_id

    def stop(self, expected_operation_id: str | None = None) -> bool:
        if not self.active:
            return False
        if (
            expected_operation_id is not None
            and expected_operation_id != self._operation_id
        ):
            return False
        if self._state is SpeechState.CANCELLING:
            return True
        self._state = SpeechState.CANCELLING
        self._finish(SpeechOutcome.CANCELLED, "cancelled")
        return True

    def complete(self) -> bool:
        if not self.active:
            return False
        self._finish(SpeechOutcome.COMPLETED, "playback_completed")
        return True

    def fail(self) -> None:
        self._finish(SpeechOutcome.FAILED, "simulated_failure")

    def timeout(self) -> None:
        self._finish(SpeechOutcome.TIMEOUT, "simulated_timeout")

    def _finish(self, outcome: SpeechOutcome, reason: str) -> None:
        if self._operation_id is None:
            return
        operation_id = self._operation_id
        self._completion = SpeechCompletion(
            operation_id, outcome, reason, None
        )
        self._operation_id = None
        if self._state is not SpeechState.CLOSED:
            self._state = SpeechState.IDLE
        self._on_terminal(operation_id)

    def poll(self) -> SpeechCompletion | None:
        completion = self._completion
        self._completion = None
        return completion

    def close(self) -> None:
        if self._state is SpeechState.CLOSED:
            return
        if self.active:
            self.stop(self._operation_id)
        self._state = SpeechState.CLOSED
        self.available = False


class SimulatedPerception:
    def __init__(self) -> None:
        self._sequence = 0

    def presence_event(
        self,
        *,
        present: bool,
        observed_at: float,
        expires_at: float,
        confidence: float = 1.0,
        source: str = "simulated-perception",
        presence_key: str = "anonymous_presence",
    ) -> Event:
        self._sequence += 1
        event_id = f"{source}:{presence_key}:{observed_at}:{self._sequence}"
        return Event(
            type=EventType.PERSON_PRESENCE_OBSERVED,
            payload={
                "present": present,
                "confidence": confidence,
                "observed_at": observed_at,
                "expires_at": expires_at,
                "source": source,
                "knowledge": KnowledgeKind.OBSERVED,
            },
            event_id=event_id,
            timestamp=observed_at,
        )
