"""Composición del runtime situacional y sus imports provisionales de Cortex."""
from __future__ import annotations
from typing import Protocol
from sirah_cortex import Event, EventType, RobotPort, WorldState
from sirah_cortex.adapters.events.in_memory import InMemoryEventInbox
from sirah_cortex.services.runtime import Runtime
from .cortex_integration import CapabilityRunner
from .errors import SituationalError
from .interaction import InitiativeAction, InitiativeDecision, InteractionMemory, evaluate_initiative
from .local_commands import LocalStopRouter, StopResult
from .simulated_robot import SimulatedRobotAdapter
from .simulation import SimulatedPerception
from .speech import SpeechOutputPort
from .system import ComponentRegistry

class Clock(Protocol):
    def now(self) -> float: ...

class SituationalCoordinator:
    GREETING_TEXT = "Hola. Detecté que hay una persona presente."
    def __init__(self, *, runtime: Runtime, inbox: InMemoryEventInbox, perception: SimulatedPerception, speech: SpeechOutputPort, runner: CapabilityRunner, components: ComponentRegistry, clock: Clock, memory: InteractionMemory | None = None, cooldown_seconds: float = 30.0) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds no puede ser negativo.")
        self.runtime, self.inbox, self.perception = runtime, inbox, perception
        self.speech, self.runner, self.components, self.clock = speech, runner, components, clock
        self.memory = memory or InteractionMemory()
        self.cooldown_seconds = cooldown_seconds
        self.stop_router = LocalStopRouter()
        self._pending_presence_key = "anonymous_presence"
    def inject_presence(self, *, present: bool, presence_key: str = "anonymous_presence", duration: float = 60.0) -> int:
        now = self.clock.now()
        self.inbox.publish(self.perception.presence_event(present=present, observed_at=now, expires_at=now + duration, presence_key=presence_key))
        self._pending_presence_key = presence_key
        return self.process_events()
    def process_events(self) -> int:
        count = 0
        while True:
            result = self.runtime.process_next(timeout_seconds=0.0)
            if result is None:
                return count
            count += 1
    def evaluate(self, *, presence_key: str | None = None) -> InitiativeDecision:
        key = presence_key or self._pending_presence_key
        self.memory = self.memory.prune(self.clock.now())
        decision = evaluate_initiative(self.runtime.state, self.memory, now=self.clock.now(), tts_available=self.speech.available, presence_key=key, cooldown_seconds=self.cooldown_seconds)
        self.memory = self.memory._replace(initiative=decision.action.value, last_reason=decision.reason)
        return decision
    def evaluate_and_act(self, *, presence_key: str | None = None) -> InitiativeDecision:
        decision = self.evaluate(presence_key=presence_key)
        if decision.action is not InitiativeAction.GREET:
            return decision
        self.memory = self.memory.with_speech(decision.presence_key, self.GREETING_TEXT)
        try:
            self.speech.start(self.GREETING_TEXT)
        except SituationalError as error:
            self.memory = self.memory.cancel_pending(decision.presence_key)._replace(last_reason="tts_error")
            return InitiativeDecision(InitiativeAction.WAIT, f"tts_error:{error}", decision.presence_key)
        self.memory = self.memory._replace(last_reason=decision.reason)
        return decision
    def finish_speech(self, *, success: bool = True) -> None:
        operation = self.memory.active_speech
        self.speech.complete()
        if operation is None:
            self.memory = self.memory._replace(last_reason="speech_not_active")
        elif success:
            self.memory = self.memory.confirm(operation.presence_key, self.clock.now())
        else:
            self.memory = self.memory.cancel_pending(operation.presence_key)._replace(last_reason="tts_cancelled")
    def set_silent(self, active: bool) -> None:
        self.memory = self.memory._replace(silent_mode=active, last_reason="silent_mode_enabled" if active else "silent_mode_disabled")
    def set_autonomy(self, active: bool) -> None:
        self.memory = self.memory._replace(autonomy_active=active, last_reason="autonomy_resumed" if active else "autonomy_paused")
    def stop(self, text: str, *, request_id: str = "local-stop") -> StopResult:
        result = self.stop_router.route(text, speech=self.speech, runner=self.runner, request_id=request_id)
        if result.matched:
            self.memory = self.memory.cancel_pending()._replace(last_reason="local_stop")
        return result

def build_situational_runtime(*, robot: RobotPort | None = None, at: float = 0.0) -> tuple[Runtime, InMemoryEventInbox, RobotPort]:
    inbox = InMemoryEventInbox()
    runtime = Runtime(inbox, WorldState.initial(at))
    inbox.publish(Event(EventType.SYSTEM_STARTED, event_id="situational-system-started", timestamp=at))
    runtime.process_next(timeout_seconds=0.0)
    active = robot or SimulatedRobotAdapter()
    if not active.is_connected:
        active.connect()
        active.read_events()
    return runtime, inbox, active
