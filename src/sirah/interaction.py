"""Estado social efímero y política determinista de iniciativa."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from sirah_cortex import RobotState, WorldState

@dataclass(frozen=True, slots=True)
class GreetingRecord:
    key: str
    expires_at: float

@dataclass(frozen=True, slots=True)
class PendingSpeech:
    presence_key: str
    text: str

class InitiativeAction(str, Enum):
    GREET = "greet"
    WAIT = "wait"
    DISCARD = "discard"

@dataclass(frozen=True, slots=True)
class InitiativeDecision:
    action: InitiativeAction
    reason: str
    presence_key: str

@dataclass(frozen=True, slots=True)
class InteractionMemory:
    confirmed_greetings: tuple[GreetingRecord, ...] = ()
    active_speech: PendingSpeech | None = None
    last_greeting_at: float | None = None
    silent_mode: bool = False
    autonomy_active: bool = True
    initiative: str | None = None
    last_reason: str | None = None
    greeting_memory_ttl_seconds: float = 600.0
    maximum_remembered_presences: int = 128

    def __post_init__(self) -> None:
        if self.greeting_memory_ttl_seconds <= 0:
            raise ValueError("greeting_memory_ttl_seconds debe ser mayor que cero.")
        if self.maximum_remembered_presences <= 0:
            raise ValueError("maximum_remembered_presences debe ser mayor que cero.")

    @property
    def pending_greetings(self) -> frozenset[str]:
        if self.active_speech is None:
            return frozenset()
        return frozenset({self.active_speech.presence_key})

    @property
    def tts_active(self) -> bool:
        return self.active_speech is not None

    def prune(self, now: float) -> "InteractionMemory":
        records = tuple(r for r in self.confirmed_greetings if r.expires_at > now)
        records = tuple(
            sorted(records, key=lambda r: (r.expires_at, r.key))[
                -self.maximum_remembered_presences :
            ]
        )
        return self._replace(confirmed_greetings=records)

    def pending(self, key: str) -> "InteractionMemory":
        if self.active_speech is not None:
            raise ValueError("Ya existe una operación de voz activa.")
        return self._replace(active_speech=PendingSpeech(key, ""))

    def with_speech(self, key: str, text: str) -> "InteractionMemory":
        if self.active_speech is not None:
            raise ValueError("Ya existe una operación de voz activa.")
        return self._replace(active_speech=PendingSpeech(key, text))

    def confirm(self, key: str, now: float) -> "InteractionMemory":
        current = self.prune(now)
        records = tuple(r for r in current.confirmed_greetings if r.key != key)
        records += (GreetingRecord(key, now + self.greeting_memory_ttl_seconds),)
        records = tuple(
            sorted(records, key=lambda r: (r.expires_at, r.key))[
                -self.maximum_remembered_presences :
            ]
        )
        return current._replace(
            active_speech=None,
            confirmed_greetings=records,
            last_greeting_at=now,
            initiative="greet",
        )

    def cancel_pending(self, key: str | None = None) -> "InteractionMemory":
        if self.active_speech is None:
            return self._replace(active_speech=None)
        if key is None or self.active_speech.presence_key == key:
            return self._replace(active_speech=None)
        return self

    def _replace(self, **changes: object) -> "InteractionMemory":
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        values.update(changes)
        return InteractionMemory(**values)

def evaluate_initiative(state: WorldState, memory: InteractionMemory, *, now: float, tts_available: bool, presence_key: str = "anonymous_presence", cooldown_seconds: float = 30.0) -> InitiativeDecision:
    memory = memory.prune(now)
    observation = state.person_observation
    if observation is None or not observation.is_current(now):
        return InitiativeDecision(InitiativeAction.WAIT, "presence_not_current", presence_key)
    if not observation.present:
        return InitiativeDecision(InitiativeAction.WAIT, "person_absent", presence_key)
    if not memory.autonomy_active:
        return InitiativeDecision(InitiativeAction.WAIT, "autonomy_paused", presence_key)
    if memory.silent_mode:
        return InitiativeDecision(InitiativeAction.WAIT, "silent_mode", presence_key)
    if state.emergency_stop_active:
        return InitiativeDecision(InitiativeAction.WAIT, "emergency_active", presence_key)
    if state.active_task_id is not None or state.robot_state is not RobotState.IDLE:
        return InitiativeDecision(InitiativeAction.WAIT, "incompatible_interaction", presence_key)
    if memory.tts_active or presence_key in memory.pending_greetings:
        return InitiativeDecision(InitiativeAction.WAIT, "greeting_pending", presence_key)
    if any(r.key == presence_key for r in memory.confirmed_greetings):
        return InitiativeDecision(InitiativeAction.DISCARD, "already_greeted", presence_key)
    if memory.last_greeting_at is not None and now - memory.last_greeting_at < cooldown_seconds:
        return InitiativeDecision(InitiativeAction.WAIT, "greet_cooldown", presence_key)
    if not tts_available:
        return InitiativeDecision(InitiativeAction.WAIT, "tts_unavailable", presence_key)
    return InitiativeDecision(InitiativeAction.GREET, "person_present_not_greeted", presence_key)
