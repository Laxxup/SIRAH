"""build_system() — single factory for all deployment profiles.

Profiles:
    DEV_LAPTOP      → Everything simulated, no hardware, deterministic.
    DEV_DISTRIBUTED → Laptop orchestrates, Pi 4B serves I/O.
"""

from __future__ import annotations

from enum import Enum, auto

from sirah.action.capabilities import CapabilityCatalog, CapabilityPolicy
from sirah.action.runner import ActionRunner
from sirah.action.simulated import SimulatedRobot
from sirah.autonomy.mood_engine import MoodEngine
from sirah.bridge.laptop_client import LaptopClient
from sirah.core.context import ConversationContext
from sirah.core.orchestrator import SirahOrchestrator
from sirah.core.registry import ComponentRegistry
from sirah.intelligence.demo_adapter import LaboratoryIntelligence
from sirah.intelligence.fake_adapter import FakeIntelligence
from sirah.intelligence.groq_adapter import GroqIntelligence
from sirah.intelligence.port import IntelligencePort
from sirah.perception.port import PerceptionPort
from sirah.perception.simulated import SimulatedPerception
from sirah.social.situational import SituationalCoordinator
from sirah.voice.port import SpeechInputPort, SpeechOutputPort
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput

__all__ = ["SystemProfile", "build_system", "SystemAssembly"]


class SystemProfile(Enum):
    DEV_LAPTOP = auto()
    DEV_DISTRIBUTED = auto()


class SystemAssembly:
    def __init__(
        self,
        orchestrator: SirahOrchestrator,
        situational: SituationalCoordinator | None = None,
        intelligence: IntelligencePort | None = None,
        perception: PerceptionPort | None = None,
        speech_input: SpeechInputPort | None = None,
        speech_output: SpeechOutputPort | None = None,
        capabilities: CapabilityCatalog | None = None,
        policy: CapabilityPolicy | None = None,
        runner: ActionRunner | None = None,
        registry: ComponentRegistry | None = None,
        bridge: LaptopClient | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.situational = situational
        self.intelligence = intelligence
        self.perception = perception
        self.speech_input = speech_input
        self.speech_output = speech_output
        self.capabilities = capabilities
        self.policy = policy
        self.runner = runner
        self.registry = registry
        self.bridge = bridge


def build_system(
    profile: SystemProfile = SystemProfile.DEV_LAPTOP,
    intelligence_type: str = "fake",
    groq_api_key: str | None = None,
    groq_model: str = "llama-3.3-70b-versatile",
    ollama_model: str = "llama3.2:3b",
    edge_host: str = "raspberrypi.local",
    edge_port: int = 8765,
    tts: str = "fake",
    piper_voice: str = "es_ES-sharvard-medium",
    mood_enabled: bool = True,
) -> SystemAssembly:
    context = ConversationContext(max_messages=16)
    registry = ComponentRegistry()
    robot = SimulatedRobot()
    catalog = CapabilityCatalog()
    policy = CapabilityPolicy()
    runner = ActionRunner(robot=robot)

    intelligence: IntelligencePort
    if intelligence_type == "groq":
        intelligence = GroqIntelligence(
            api_key=groq_api_key,
            model=groq_model,
        )
    elif intelligence_type == "laboratory":
        intelligence = LaboratoryIntelligence()
    elif intelligence_type == "scripted":
        intelligence = FakeIntelligence(
            scripted=[
                "¡Hola! Soy SIRAH. ¿En qué puedo ayudarte?",
                "Claro, lo haré con gusto.",
                "¡Hecho!",
            ]
        )
    else:
        intelligence = FakeIntelligence()

    perception: PerceptionPort | None = SimulatedPerception()
    speech_input: SpeechInputPort | None = FakeSpeechInput()

    if tts == "piper":
        from sirah.voice.tts_piper import PiperTTS
        speech_output: SpeechOutputPort | None = PiperTTS(model_name=piper_voice)
    elif tts == "gtts":
        from sirah.voice.tts_gtts import GTTSTTS
        speech_output = GTTSTTS()
    else:
        speech_output = FakeSpeechOutput()

    mood = MoodEngine() if mood_enabled else None

    orchestrator = SirahOrchestrator(
        intelligence=intelligence,
        perception=perception,
        speech_input=speech_input,
        speech_output=speech_output,
        capabilities=catalog,
        policy=policy,
        action_runner=runner,
        cortex=None,
        context=context,
        registry=registry,
        mood=mood,
    )

    situational = SituationalCoordinator(
        orchestrator=orchestrator,
        perception=perception,
        speech=speech_output,
        interval_s=0.5,
        silent=False,
    )

    bridge: LaptopClient | None = None
    if profile == SystemProfile.DEV_DISTRIBUTED:
        bridge = LaptopClient(edge_host=edge_host, edge_port=edge_port)

    return SystemAssembly(
        orchestrator=orchestrator,
        situational=situational,
        intelligence=intelligence,
        perception=perception,
        speech_input=speech_input,
        speech_output=speech_output,
        capabilities=catalog,
        policy=policy,
        runner=runner,
        registry=registry,
        bridge=bridge,
    )
