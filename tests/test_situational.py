"""Pruebas del circuito Cortex-presencia-iniciativa-TTS-stop."""

import pytest

from sirah import CapabilityRunner
from sirah.interaction import (
    InitiativeAction,
    InteractionMemory,
    PendingSpeech,
    evaluate_initiative,
)
from sirah import create_default_catalog
from sirah.local_commands import LocalStopRouter
from sirah.simulation import FakeClock, FakeSpeechOutput, SimulatedPerception
from sirah.situational_runtime import SituationalCoordinator, build_situational_runtime
from sirah.speech import SpeechFailure
from sirah.intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
)
from sirah.system import ComponentRegistry


def coordinator(
    *,
    clock: FakeClock | None = None,
    speech: FakeSpeechOutput | None = None,
    cooldown: float = 30.0,
) -> tuple[SituationalCoordinator, FakeClock, FakeSpeechOutput]:
    runtime, inbox, robot = build_situational_runtime(at=0.0)
    active_clock = clock or FakeClock(0.0)
    active_speech = speech or FakeSpeechOutput()
    return (
        SituationalCoordinator(
            runtime=runtime,
            inbox=inbox,
            perception=SimulatedPerception(),
            speech=active_speech,
            runner=CapabilityRunner(create_default_catalog(), robot),
            components=ComponentRegistry(),
            clock=active_clock,
            cooldown_seconds=cooldown,
        ),
        active_clock,
        active_speech,
    )


def test_presence_enters_cortex_runtime_and_updates_world_state() -> None:
    service, _, _ = coordinator()
    service.inject_presence(present=True, duration=10.0)
    assert service.runtime.state.person_presence(0.0) is True
    assert service.runtime.state.version > 1


def test_presence_proposes_and_records_deterministic_greeting() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=True)
    decision = service.evaluate_and_act(presence_key="person:one")
    assert decision.action is InitiativeAction.GREET
    assert speech.spoken_texts == [service.GREETING_TEXT]
    assert "person:one" in service.memory.pending_greetings
    service.finish_speech()
    assert any(record.key == "person:one" for record in service.memory.confirmed_greetings)


def test_absence_does_not_propose_greeting() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=False)
    assert service.evaluate_and_act().action is InitiativeAction.WAIT
    assert speech.spoken_texts == []


@pytest.mark.parametrize(
    "change",
    ["silent", "autonomy"],
)
def test_silent_or_paused_autonomy_blocks_greeting(change: str) -> None:
    service, _, speech = coordinator()
    if change == "silent":
        service.set_silent(True)
    else:
        service.set_autonomy(False)
    service.inject_presence(present=True)
    assert service.evaluate_and_act().action is InitiativeAction.WAIT
    assert speech.spoken_texts == []


def test_unavailable_tts_degrades_without_marking_greeted() -> None:
    service, _, speech = coordinator(speech=FakeSpeechOutput(available=False))
    service.inject_presence(present=True)
    decision = service.evaluate_and_act(presence_key="person:one")
    assert decision.action is InitiativeAction.WAIT
    assert decision.reason == "tts_unavailable"
    assert service.memory.confirmed_greetings == ()
    assert speech.errors == []


def test_repeated_observation_does_not_repeat_greeting() -> None:
    service, clock, speech = coordinator()
    service.inject_presence(present=True, presence_key="person:one")
    assert service.evaluate_and_act(presence_key="person:one").action is InitiativeAction.GREET
    service.finish_speech()
    clock.advance(1.0)
    service.inject_presence(present=True, presence_key="person:one")
    assert service.evaluate_and_act(presence_key="person:one").reason == "already_greeted"
    assert len(speech.spoken_texts) == 1


def test_cooldown_blocks_new_presence_then_expires() -> None:
    service, clock, speech = coordinator(cooldown=10.0)
    service.inject_presence(present=True, presence_key="person:one")
    service.evaluate_and_act(presence_key="person:one")
    service.finish_speech()
    service.inject_presence(present=True, presence_key="person:two")
    assert service.evaluate_and_act(presence_key="person:two").reason == "greet_cooldown"
    clock.advance(10.0)
    assert service.evaluate_and_act(presence_key="person:two").action is InitiativeAction.GREET
    assert len(speech.spoken_texts) == 2


def test_expired_observation_does_not_trigger() -> None:
    service, clock, _ = coordinator()
    service.inject_presence(present=True, duration=1.0)
    clock.advance(2.0)
    assert service.evaluate().reason == "presence_not_current"


def test_fake_tts_can_be_cancelled() -> None:
    speech = FakeSpeechOutput()
    speech.start("hola")
    assert speech.active
    speech.stop()
    assert not speech.active


def test_stop_is_local_idempotent_and_does_not_need_intelligence() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=True)
    service.evaluate_and_act()
    result = service.stop("detente")
    assert result.matched
    assert result.tts_cancelled
    assert result.robot_result and result.robot_result.succeeded
    assert not speech.active
    second = service.stop("stop")
    assert second.matched
    assert second.robot_result and second.robot_result.succeeded


def test_stop_router_is_conservative() -> None:
    router = LocalStopRouter()
    assert router.matches("detente")
    assert router.matches("PARA!")
    assert not router.matches("¿Qué significa detener?")


class CountingIntelligence:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self.calls += 1
        return IntelligenceResponse(
            IntelligenceDecision(DecisionType.RESPOND_ONLY, "respuesta"),
            "counting",
            "test",
        )


def test_local_stop_has_no_intelligence_dependency() -> None:
    intelligence = CountingIntelligence()
    router = LocalStopRouter()
    speech = FakeSpeechOutput()
    service, _, _ = coordinator(speech=speech)
    result = router.route(
        "stop",
        speech=speech,
        runner=service.runner,
        request_id="stop-test",
    )
    assert result.matched
    assert intelligence.calls == 0


def test_tts_failure_does_not_destroy_world_state() -> None:
    service, _, _ = coordinator(speech=FakeSpeechOutput(failure=SpeechFailure.FAILED))
    service.inject_presence(present=True)
    service.evaluate_and_act()
    assert service.runtime.state.person_presence(0.0) is True


def test_policy_is_pure_and_uses_cortex_state() -> None:
    service, _, _ = coordinator()
    service.inject_presence(present=True)
    decision = evaluate_initiative(
        service.runtime.state,
        InteractionMemory(),
        now=0.0,
        tts_available=True,
    )
    assert decision.action is InitiativeAction.GREET


def test_pending_greeting_blocks_duplicate_until_completion() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=True, presence_key="presence:one")
    service.evaluate_and_act(presence_key="presence:one")
    assert service.evaluate(presence_key="presence:one").reason == "greeting_pending"
    assert speech.active


def test_cancelled_or_failed_tts_does_not_confirm_greeting() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=True, presence_key="presence:one")
    service.evaluate_and_act(presence_key="presence:one")
    service.stop("stop")
    assert service.memory.confirmed_greetings == ()
    assert service.memory.pending_greetings == frozenset()
    assert not speech.active


def test_greeting_memory_expires_and_is_pruned() -> None:
    service, clock, _ = coordinator()
    service.memory = InteractionMemory(
        greeting_memory_ttl_seconds=5.0,
        maximum_remembered_presences=2,
    )
    for key in ("a", "b", "c"):
        service.inject_presence(present=True, presence_key=key)
        service.evaluate_and_act(presence_key=key)
        service.finish_speech()
        clock.advance(30.0)
    assert len(service.memory.confirmed_greetings) <= 2
    clock.advance(6.0)
    assert service.memory.prune(clock.now()).confirmed_greetings == ()


def test_social_greeting_does_not_require_arm_capability() -> None:
    service, _, speech = coordinator()
    service.inject_presence(present=True, presence_key="anonymous_presence")
    assert service.evaluate_and_act().action is InitiativeAction.GREET
    service.finish_speech()
    assert speech.spoken_texts == [service.GREETING_TEXT]


@pytest.mark.parametrize("maximum", [1, 128])
def test_confirmed_memory_never_exceeds_configured_limit(maximum: int) -> None:
    memory = InteractionMemory(maximum_remembered_presences=maximum)
    for index in range(maximum + 3):
        memory = memory.confirm(f"presence:{index}", float(index))
    assert len(memory.confirmed_greetings) <= maximum


@pytest.mark.parametrize("kwargs", [
    {"maximum_remembered_presences": 0},
    {"maximum_remembered_presences": -1},
    {"greeting_memory_ttl_seconds": 0},
    {"greeting_memory_ttl_seconds": -1},
])
def test_invalid_memory_configuration_is_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        InteractionMemory(**kwargs)


def test_negative_cooldown_is_rejected() -> None:
    with pytest.raises(ValueError):
        coordinator(cooldown=-1)


def test_pruning_is_persistent_and_visible_in_snapshot() -> None:
    service, clock, _ = coordinator()
    service.memory = service.memory.confirm("presence:old", 0.0)
    clock.advance(601.0)
    service.evaluate()
    assert service.memory.confirmed_greetings == ()


def test_active_speech_is_explicit_and_finish_without_operation_is_safe() -> None:
    service, _, _ = coordinator()
    service.finish_speech()
    assert service.memory.active_speech is None
    service.inject_presence(present=True, presence_key="presence:one")
    service.evaluate_and_act(presence_key="presence:one")
    assert service.memory.active_speech == PendingSpeech("presence:one", service.GREETING_TEXT)
    service.finish_speech()
    assert service.memory.active_speech is None


def test_same_timestamp_events_have_distinct_ids() -> None:
    perception = SimulatedPerception()
    first = perception.presence_event(present=True, observed_at=0.0, expires_at=1.0, presence_key="a")
    second = perception.presence_event(present=True, observed_at=0.0, expires_at=1.0, presence_key="a")
    third = perception.presence_event(present=True, observed_at=0.0, expires_at=1.0, presence_key="b")
    assert len({first.event_id, second.event_id, third.event_id}) == 3
