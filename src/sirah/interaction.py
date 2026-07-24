"""Estado social efímero y política determinista de iniciativa."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from sirah_cortex import WorldState
from sirah_cortex.domain.robot_state import RobotState

@dataclass(frozen=True, slots=True)
class GreetingRecord:
    key: str
    expires_at: float

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
    pending_greetings: frozenset[str] = frozenset()
    confirmed_greetings: tuple[GreetingRecord, ...] = ()
    last_greeting_at: float | None = None
    silent_mode: bool = False
    autonomy_active: bool = True
    initiative: str | None = None
    tts_active: bool = False
    last_reason: str | None = None
    greeting_memory_ttl_seconds: float = 600.0
    maximum_remembered_presences: int = 128

    def prune(self, now: float) -> "InteractionMemory":
        records = tuple(r for r in self.confirmed_greetings if r.expires_at > now)
        records = tuple(
            sorted(records, key=lambda r: (r.expires_at, r.key))[
                -self.maximum_remembered_presences :
            ]
        )
        return self._replace(confirmed_greetings=records)

    def pending(self, key: str) -> "InteractionMemory":
        return self._replace(pending_greetings=self.pending_greetings | {key})

    def confirm(self, key: str, now: float) -> "InteractionMemory":
        current = self.prune(now)
        records = tuple(r for r in current.confirmed_greetings if r.key != key)
        records += (GreetingRecord(key, now + self.greeting_memory_ttl_seconds),)
        return current._replace(
            pending_greetings=current.pending_greetings - {key},
            confirmed_greetings=records,
            last_greeting_at=now,
            initiative="greet",
            tts_active=False,
        )

    def cancel_pending(self, key: str | None = None) -> "InteractionMemory":
        pending = frozenset() if key is None else self.pending_greetings - {key}
        return self._replace(pending_greetings=pending, tts_active=False)

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
