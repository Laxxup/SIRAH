"""Test SituationalCoordinator."""

from __future__ import annotations

import asyncio

import pytest

from sirah.action.capabilities import CapabilityCatalog, CapabilityPolicy
from sirah.action.runner import ActionRunner
from sirah.action.simulated import SimulatedRobot
from sirah.core.orchestrator import SirahOrchestrator
from sirah.intelligence.fake_adapter import FakeIntelligence
from sirah.perception.simulated import SimulatedPerception
from sirah.social.situational import SituationalCoordinator
from sirah.types import FaceDetection
from sirah.voice.audio_service import AudioTurnService
from sirah.voice.coordinator import AudioTurnCoordinator
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput


def voice(output: FakeSpeechOutput) -> AudioTurnService:
    async def respond(_: str) -> str:
        return ""

    return AudioTurnService(
        capture_device="test-capture",
        speech_input=FakeSpeechInput(),
        speech_output=output,
        coordinator=AudioTurnCoordinator(),
        respond=respond,
    )


@pytest.mark.asyncio
async def test_situational_starts_and_stops() -> None:
    orch = SirahOrchestrator(
        intelligence=FakeIntelligence(),
        perception=SimulatedPerception(),
        speech_input=FakeSpeechInput(),
        speech_output=FakeSpeechOutput(),
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )
    coord = SituationalCoordinator(
        orchestrator=orch,
        perception=SimulatedPerception(),
        interval_s=0.1,
        silent=True,
    )
    await orch.start()
    await coord.start()
    assert coord.memory.is_empty
    await asyncio.sleep(0.3)
    await coord.stop()
    await orch.stop()


@pytest.mark.asyncio
async def test_situational_silent_no_initiative() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    sim_perception = SimulatedPerception(scripted_faces=[(face,)])
    orch = SirahOrchestrator(
        intelligence=FakeIntelligence(),
        perception=sim_perception,
        speech_input=FakeSpeechInput(),
        speech_output=FakeSpeechOutput(),
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )
    coord = SituationalCoordinator(
        orchestrator=orch,
        perception=sim_perception,
        interval_s=0.05,
        silent=True,
    )
    await orch.start()
    await coord.start()
    await asyncio.sleep(0.2)
    await coord.stop()
    await orch.stop()
    assert coord.memory.greet_count == 0


@pytest.mark.asyncio
async def test_situational_greets_when_face_detected() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    sim_perception = SimulatedPerception(scripted_faces=[(face,)])
    speech_output = FakeSpeechOutput()

    orch = SirahOrchestrator(
        intelligence=FakeIntelligence(),
        perception=sim_perception,
        speech_input=FakeSpeechInput(),
        speech_output=speech_output,
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )
    coord = SituationalCoordinator(
        orchestrator=orch,
        perception=sim_perception,
        voice=voice(speech_output),
        interval_s=0.05,
        silent=False,
    )
    await orch.start()
    await coord.start()
    await asyncio.sleep(0.3)
    await coord.stop()
    await orch.stop()
    assert coord.memory.greet_count >= 1
    assert len(speech_output.spoken) >= 1


@pytest.mark.asyncio
async def test_situational_conversation_active_suppresses() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    sim_perception = SimulatedPerception(scripted_faces=[(face,)])
    orch = SirahOrchestrator(
        intelligence=FakeIntelligence(),
        perception=sim_perception,
        speech_input=FakeSpeechInput(),
        speech_output=FakeSpeechOutput(),
        capabilities=CapabilityCatalog(),
        policy=CapabilityPolicy(),
        action_runner=ActionRunner(robot=SimulatedRobot()),
    )
    coord = SituationalCoordinator(
        orchestrator=orch,
        perception=sim_perception,
        interval_s=0.05,
        silent=False,
    )
    coord.mark_conversation_active(True)
    await orch.start()
    await coord.start()
    await asyncio.sleep(0.2)
    await coord.stop()
    await orch.stop()
    assert coord.memory.greet_count == 0
