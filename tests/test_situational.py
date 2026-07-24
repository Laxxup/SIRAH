"""Pruebas del circuito Cortex-presencia-iniciativa-TTS-stop."""

import pytest

from sirah import (
    CapabilityRunner,
    FakeClock,
    FakeSpeechOutput,
    InitiativeAction,
    InteractionMemory,
    LocalStopRouter,
    SimulatedPerception,
    SituationalCoordinator,
    SpeechFailure,
    build_situational_runtime,
    create_default_catalog,
    evaluate_initiative,
)
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
    assert "person:one" in service.memory.greeted_keys


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
    assert service.memory.greeted_keys == frozenset()
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
