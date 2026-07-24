"""Adaptadores simulados del circuito situacional."""
from __future__ import annotations
from dataclasses import dataclass, field
from time import monotonic
from sirah_cortex import Event, EventType
from sirah_cortex.domain.world_state import KnowledgeKind
from .errors import SituationalError
from .speech import SpeechFailure

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
    def now(self) -> float: return monotonic()

@dataclass(slots=True)
class FakeSpeechOutput:
    available: bool = True
    failure: SpeechFailure = SpeechFailure.NONE
    active: bool = False
    spoken_texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    def start(self, text: str) -> None:
        if not self.available or self.failure is SpeechFailure.UNAVAILABLE:
            self.errors.append("tts_unavailable")
            raise SituationalError("TTS no disponible.")
        if self.failure is SpeechFailure.FAILED:
            self.errors.append("tts_failed")
            raise SituationalError("TTS simulado falló.")
        if self.active:
            raise SituationalError("TTS ya está activo.")
        self.spoken_texts.append(text)
        self.active = True
    def stop(self) -> None:
        self.active = False
    def complete(self) -> None:
        self.active = False

class SimulatedPerception:
    def presence_event(self, *, present: bool, observed_at: float, expires_at: float, confidence: float = 1.0, source: str = "simulated-perception") -> Event:
        return Event(type=EventType.PERSON_PRESENCE_OBSERVED, payload={"present": present, "confidence": confidence, "observed_at": observed_at, "expires_at": expires_at, "source": source, "knowledge": KnowledgeKind.OBSERVED}, event_id=f"simulated-presence:{observed_at}:{present}", timestamp=observed_at)
