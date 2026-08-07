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
from sirah.types import ComponentId, ComponentKind, ComponentStatus
from sirah.voice.port import SpeechInputPort, SpeechOutputPort
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput

__all__ = ["SystemProfile", "SystemAssembly"]

_RUNTIME_ASSEMBLY_TOKEN = object()


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
    ollama_base_url: str | None = None,
    ollama_model: str = "gpt-oss:120b-cloud",
    ollama_fallback_model: str | None = "gemma3:4b",
    ollama_timeout: float = 30.0,
    edge_host: str = "raspberrypi.local",
    edge_port: int = 8765,
    tts: str = "fake",
    stt: str = "fake",
    piper_voice: str = "es_ES-sharvard-medium",
    piper_model_path: str | None = None,
    piper_config_path: str | None = None,
    kokoro_url: str | None = None,
    kokoro_model: str = "kokoro",
    kokoro_voice: str = "ef_dora",
    kokoro_speed: float = 1.0,
    kokoro_timeout: float = 30.0,
    output_device: str | None = None,
    mood_enabled: bool = True,
    personality_dir: str | None = None,
    *,
    _runtime_token: object | None = None,
) -> SystemAssembly:
    from sirah.errors import RuntimeAssemblyAccessError, RuntimeConfigurationError

    if _runtime_token is not _RUNTIME_ASSEMBLY_TOKEN:
        raise RuntimeAssemblyAccessError("system assembly is owned by SirahRuntime")
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
    elif intelligence_type == "ollama":
        from sirah.intelligence.ollama_adapter import OllamaIntelligence

        intelligence = OllamaIntelligence(
            base_url=ollama_base_url or "http://127.0.0.1:11434",
            model=ollama_model,
            fallback_model=ollama_fallback_model,
            timeout=ollama_timeout,
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
    if stt == "whisper":
        from sirah.voice.stt_whisper import WhisperSTT

        speech_input: SpeechInputPort | None = WhisperSTT()
    else:
        speech_input = FakeSpeechInput()

    if tts == "piper":
        from pathlib import Path

        from sirah.voice.tts_piper import AplayPlayer, PiperTTS

        if not (piper_model_path and piper_config_path and output_device):
            raise RuntimeAssemblyAccessError("Piper requires runtime audio configuration")
        speech_output: SpeechOutputPort | None = PiperTTS(
            model_path=Path(piper_model_path),
            config_path=Path(piper_config_path),
            player=AplayPlayer(output_device),
            on_failure=lambda: registry.update(
                ComponentId(ComponentKind.VOICE, "speech"),
                ComponentStatus.DEGRADED,
                "Piper unavailable",
            ),
        )
    elif tts == "kokoro_http":
        from sirah.voice.tts_kokoro import KokoroHTTPTTS
        from sirah.voice.tts_piper import AplayPlayer

        if not output_device:
            raise RuntimeAssemblyAccessError("Kokoro requires runtime audio configuration")
        if not kokoro_url:
            raise RuntimeAssemblyAccessError("Kokoro requires SIRAH_KOKORO_URL")
        speech_output = KokoroHTTPTTS(
            base_url=kokoro_url,
            model=kokoro_model,
            voice=kokoro_voice,
            speed=kokoro_speed,
            timeout=kokoro_timeout,
            player=AplayPlayer(output_device),
            on_failure=lambda: registry.update(
                ComponentId(ComponentKind.VOICE, "speech"),
                ComponentStatus.DEGRADED,
                "Kokoro unavailable",
            ),
        )
    elif tts == "gtts":
        from sirah.voice.tts_gtts import GTTSTTS
        speech_output = GTTSTTS()
    else:
        speech_output = FakeSpeechOutput()

    mood = MoodEngine() if mood_enabled else None

    personality = None
    if personality_dir:
        from sirah.personality.loader import PersonalityLoader
        try:
            personality = PersonalityLoader(personality_dir).load()
        except Exception as exc:
            raise RuntimeConfigurationError(f"personality load failed: {exc}") from exc

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
        personality=personality,
    )

    situational = SituationalCoordinator(
        orchestrator=orchestrator,
        perception=perception,
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
