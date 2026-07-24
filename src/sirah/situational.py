"""Circuito vertical de percepción simulada e iniciativa situada.

Los imports de Runtime e InMemoryEventInbox son provisionales porque Cortex no
los exporta todavía desde su fachada raíz. Se mantienen encapsulados aquí.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Protocol

from sirah_cortex import Event, EventType, RobotPort, WorldState
from sirah_cortex.adapters.events.in_memory import InMemoryEventInbox
from sirah_cortex.domain.robot_state import RobotState
from sirah_cortex.domain.world_state import KnowledgeKind
from sirah_cortex.services.runtime import Runtime

from .capabilities import CapabilityRequest
from .cortex_integration import CapabilityExecutionResult, CapabilityRunner
from .errors import CapabilityRejectedError, SirahApplicationError
from .simulated_robot import SimulatedRobotAdapter
from .system import ComponentRegistry


class SituationalError(SirahApplicationError):
    """Error controlado del circuito situado."""


class Clock(Protocol):
    def now(self) -> float:
        """Devuelve tiempo monotónico en segundos."""
        ...


class MonotonicClock:
    def now(self) -> float:
        return monotonic()


class FakeClock:
    """Reloj manual para pruebas deterministas."""

    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds no puede ser negativo.")
        self.value += seconds


class SimulatedPerception:
    """Produce eventos de presencia, sin escribir WorldState."""

    def presence_event(
        self,
        *,
        present: bool,
        observed_at: float,
        expires_at: float,
        confidence: float = 1.0,
        source: str = "simulated-perception",
    ) -> Event:
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
            event_id=f"simulated-presence:{observed_at}:{present}",
            timestamp=observed_at,
        )


class SpeechPort(Protocol):
    @property
    def active(self) -> bool:
        ...

    @property
    def available(self) -> bool:
        ...

    def start(self, text: str) -> None:
        ...

    def stop(self) -> None:
        ...

    def complete(self) -> None:
        ...


class SpeechFailure(str, Enum):
    NONE = "none"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(slots=True)
class FakeSpeechOutput:
    """TTS falso síncrono: registra texto, no reproduce audio."""

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


@dataclass(frozen=True, slots=True)
class InteractionMemory:
    """Estado de producto que no pertenece al WorldState genérico de Cortex."""

    greeted_keys: frozenset[str] = frozenset()
    last_greet_at: float | None = None
    silent_mode: bool = False
    autonomy_active: bool = True
    initiative: str | None = None
    tts_active: bool = False
    last_reason: str | None = None

    def greet(self, key: str, at: float, *, reason: str) -> "InteractionMemory":
        return InteractionMemory(
            greeted_keys=self.greeted_keys | {key},
            last_greet_at=at,
            silent_mode=self.silent_mode,
            autonomy_active=self.autonomy_active,
            initiative="greet",
            tts_active=True,
            last_reason=reason,
        )

    def with_tts(self, active: bool, *, reason: str | None = None) -> "InteractionMemory":
        return InteractionMemory(
            greeted_keys=self.greeted_keys,
            last_greet_at=self.last_greet_at,
            silent_mode=self.silent_mode,
            autonomy_active=self.autonomy_active,
            initiative=self.initiative,
            tts_active=active,
            last_reason=reason or self.last_reason,
        )


class InitiativeAction(str, Enum):
    GREET = "greet"
    WAIT = "wait"
    DISCARD = "discard"


@dataclass(frozen=True, slots=True)
class InitiativeDecision:
    action: InitiativeAction
    reason: str
    presence_key: str


def evaluate_initiative(
    state: WorldState,
    memory: InteractionMemory,
    *,
    now: float,
    tts_available: bool,
    presence_key: str = "presence:current",
    cooldown_seconds: float = 30.0,
) -> InitiativeDecision:
    """Decide saludo sin IA ni efectos laterales."""

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
    if memory.tts_active:
        return InitiativeDecision(InitiativeAction.WAIT, "tts_active", presence_key)
    if presence_key in memory.greeted_keys:
        return InitiativeDecision(InitiativeAction.DISCARD, "already_greeted", presence_key)
    if memory.last_greet_at is not None and now - memory.last_greet_at < cooldown_seconds:
        return InitiativeDecision(InitiativeAction.WAIT, "greet_cooldown", presence_key)
    if not tts_available:
        return InitiativeDecision(InitiativeAction.WAIT, "tts_unavailable", presence_key)
    return InitiativeDecision(InitiativeAction.GREET, "person_present_not_greeted", presence_key)


@dataclass(frozen=True, slots=True)
class StopResult:
    matched: bool
    tts_cancelled: bool
    robot_result: CapabilityExecutionResult | None
    reason: str


class LocalStopRouter:
    """Router conservador: solo frases exactas llegan al stop local."""

    _STOP_WORDS = frozenset({"stop", "para", "detente", "detén"})

    def matches(self, text: str) -> bool:
        return text.strip().casefold().rstrip(".!?") in self._STOP_WORDS

    def route(
        self,
        text: str,
        *,
        speech: SpeechPort,
        runner: CapabilityRunner,
        request_id: str,
    ) -> StopResult:
        if not self.matches(text):
            return StopResult(False, False, None, "not_local_stop")
        was_active = speech.active
        speech.stop()
        result: CapabilityExecutionResult | None = None
        try:
            result = runner.run(CapabilityRequest(request_id, "robot.stop"))
        except CapabilityRejectedError:
            result = None
        return StopResult(True, was_active, result, "local_stop")


class SituationalCoordinator:
    """Compone Runtime, percepción, iniciativa, TTS y stop local."""

    GREETING_TEXT = "Hola. Detecté que hay una persona presente."

    def __init__(
        self,
        *,
        runtime: Runtime,
        inbox: InMemoryEventInbox,
        perception: SimulatedPerception,
        speech: SpeechPort,
        runner: CapabilityRunner,
        components: ComponentRegistry,
        clock: Clock,
        memory: InteractionMemory | None = None,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self.runtime = runtime
        self.inbox = inbox
        self.perception = perception
        self.speech = speech
        self.runner = runner
        self.components = components
        self.clock = clock
        self.memory = memory or InteractionMemory()
        self.cooldown_seconds = cooldown_seconds
        self.stop_router = LocalStopRouter()

    def inject_presence(
        self,
        *,
        present: bool,
        presence_key: str = "presence:current",
        duration: float = 60.0,
    ) -> int:
        now = self.clock.now()
        self.inbox.publish(
            self.perception.presence_event(
                present=present,
                observed_at=now,
                expires_at=now + duration,
            )
        )
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
        pending = getattr(self, "_pending_presence_key", "presence:current")
        key = presence_key if presence_key is not None else str(pending)
        tts_available = self.speech.available
        decision = evaluate_initiative(
            self.runtime.state,
            self.memory,
            now=self.clock.now(),
            tts_available=tts_available,
            presence_key=key,
            cooldown_seconds=self.cooldown_seconds,
        )
        self.memory = InteractionMemory(
            greeted_keys=self.memory.greeted_keys,
            last_greet_at=self.memory.last_greet_at,
            silent_mode=self.memory.silent_mode,
            autonomy_active=self.memory.autonomy_active,
            initiative=decision.action.value,
            tts_active=self.speech.active,
            last_reason=decision.reason,
        )
        return decision

    def evaluate_and_act(self, *, presence_key: str | None = None) -> InitiativeDecision:
        decision = self.evaluate(presence_key=presence_key)
        if decision.action is not InitiativeAction.GREET:
            return decision
        try:
            self.speech.start(self.GREETING_TEXT)
        except SituationalError as error:
            self.memory = self.memory.with_tts(False, reason="tts_error")
            return InitiativeDecision(
                InitiativeAction.WAIT, f"tts_error:{error}", decision.presence_key
            )
        self.memory = self.memory.greet(
            decision.presence_key, self.clock.now(), reason=decision.reason
        )
        return decision

    def finish_speech(self) -> None:
        self.speech.complete()
        self.memory = self.memory.with_tts(False)

    def set_silent(self, active: bool) -> None:
        self.memory = InteractionMemory(
            greeted_keys=self.memory.greeted_keys,
            last_greet_at=self.memory.last_greet_at,
            silent_mode=active,
            autonomy_active=self.memory.autonomy_active,
            initiative=self.memory.initiative,
            tts_active=self.memory.tts_active,
            last_reason="silent_mode_enabled" if active else "silent_mode_disabled",
        )

    def set_autonomy(self, active: bool) -> None:
        self.memory = InteractionMemory(
            greeted_keys=self.memory.greeted_keys,
            last_greet_at=self.memory.last_greet_at,
            silent_mode=self.memory.silent_mode,
            autonomy_active=active,
            initiative=self.memory.initiative,
            tts_active=self.memory.tts_active,
            last_reason="autonomy_resumed" if active else "autonomy_paused",
        )

    def stop(self, text: str, *, request_id: str = "local-stop") -> StopResult:
        result = self.stop_router.route(
            text,
            speech=self.speech,
            runner=self.runner,
            request_id=request_id,
        )
        if result.matched:
            self.memory = self.memory.with_tts(False, reason="local_stop")
        return result


def build_situational_runtime(
    *,
    robot: RobotPort | None = None,
    at: float = 0.0,
) -> tuple[Runtime, InMemoryEventInbox, RobotPort]:
    """Construye Runtime público y lo deja en estado IDLE mediante eventos."""

    inbox = InMemoryEventInbox()
    runtime = Runtime(inbox, WorldState.initial(at))
    inbox.publish(
        Event(
            EventType.SYSTEM_STARTED,
            event_id="situational-system-started",
            timestamp=at,
        )
    )
    runtime.process_next(timeout_seconds=0.0)
    active_robot = robot or SimulatedRobotAdapter()
    if not active_robot.is_connected:
        active_robot.connect()
        active_robot.read_events()
    return runtime, inbox, active_robot
