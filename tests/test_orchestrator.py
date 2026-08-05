"""Test SirahOrchestrator text handling."""

from __future__ import annotations

import pytest

from sirah.core.orchestrator import SirahOrchestrator
from sirah.intelligence.fake_adapter import FakeIntelligence
from sirah.perception.simulated import SimulatedPerception
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput
from sirah.action.capabilities import CapabilityCatalog, CapabilityPolicy
from sirah.action.runner import ActionRunner
from sirah.action.simulated import SimulatedRobot


@pytest.fixture
def orchestrator() -> SirahOrchestrator:
    return SirahOrchestrator(
        intelligence=FakeIntelligence(scripted=["respuesta de prueba"]),
        perception=SimulatedPerception(),
        speech_input=FakeSpeechInput(),
        speech_output=FakeSpeechOutput(),
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )


@pytest.mark.asyncio
async def test_orchestrator_handle_text(orchestrator: SirahOrchestrator) -> None:
    await orchestrator.start()
    result = await orchestrator.handle_text("hola")
    assert result.message.role == "assistant"
    assert result.message.content == "respuesta de prueba"
    assert result.decision is not None
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_context_is_updated(orchestrator: SirahOrchestrator) -> None:
    await orchestrator.start()
    await orchestrator.handle_text("hola")
    ctx = orchestrator.context
    assert len(ctx.messages) == 2
    assert ctx.messages[0].role == "user"
    assert ctx.messages[1].role == "assistant"
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_say(orchestrator: SirahOrchestrator) -> None:
    await orchestrator.start()
    result = await orchestrator.say("hola mundo")
    assert result.success
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_snapshot(orchestrator: SirahOrchestrator) -> None:
    await orchestrator.start()
    snap = orchestrator.snapshot
    assert len(snap.components) >= 4
    await orchestrator.stop()


@pytest.mark.asyncio
async def test_orchestrator_stop_cleans_up(orchestrator: SirahOrchestrator) -> None:
    await orchestrator.start()
    assert orchestrator.is_running
    await orchestrator.stop()
    assert not orchestrator.is_running


@pytest.mark.asyncio
async def test_orchestrator_capability_decision(orchestrator: SirahOrchestrator) -> None:
    from sirah.types import IntelligenceDecision, DecisionType

    class CapabilityIntelligence:
        async def health(self) -> bool:
            return True

        async def decide(self, request):  # type: ignore[no-untyped-def]
            from sirah.types import IntelligenceResponse
            return IntelligenceResponse(
                raw_text="ok",
                decision=IntelligenceDecision(
                    decision_type=DecisionType.CONVERSATION,
                    text_response="ejecutando",
                    capability_name="robot.greet",
                    capability_params={"style": "wave"},
                ),
            )

    orch = SirahOrchestrator(
        intelligence=CapabilityIntelligence(),  # type: ignore[arg-type]
        perception=SimulatedPerception(),
        speech_input=FakeSpeechInput(),
        speech_output=FakeSpeechOutput(),
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )
    await orch.start()
    result = await orch.handle_text("saluda")
    assert result.capability_result is not None
    assert result.capability_result.success
    assert result.capability_result.capability_name == "robot.greet"
    await orch.stop()
