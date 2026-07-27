"""Fachada pública y metadata de la distribución pre-alpha."""

import ast
import subprocess
import sys
from pathlib import Path
from tomllib import load

import sirah


EXPECTED_PUBLIC_API = {
    "AudioTurnCoordinator",
    "AudioTurnDirection",
    "AudioTurnLease",
    "AudioTurnState",
    "CapabilityCatalog",
    "CapabilityDefinition",
    "CapabilityExecutionError",
    "CapabilityExecutionResult",
    "CapabilityPolicy",
    "CapabilityRejectedError",
    "CapabilityRequest",
    "CapabilityRunner",
    "ComponentId",
    "ComponentKind",
    "ComponentRegistry",
    "ComponentState",
    "ComponentStatus",
    "ConversationMessage",
    "ConversationOrchestrator",
    "ConversationResult",
    "DecisionType",
    "IntelligenceDecision",
    "IntelligencePort",
    "IntelligenceRateLimitError",
    "IntelligenceRequest",
    "IntelligenceResponse",
    "IntelligenceTimeoutError",
    "IntelligenceUnavailableError",
    "InvalidIntelligenceResponseError",
    "InitiativeAction",
    "InitiativeDecision",
    "InteractionMemory",
    "ParameterDefinition",
    "PresentContext",
    "PresentSystem",
    "PcmCapturePort",
    "PcmReadKind",
    "PcmReadResult",
    "RecognitionUpdate",
    "RecognitionUpdateKind",
    "SessionContextStore",
    "SituationalCoordinator",
    "SirahApplicationError",
    "SpeechOutputPort",
    "SpeechInputState",
    "SpeechRecognitionEvent",
    "SpeechRecognitionEventKind",
    "SpeechRecognizerPort",
    "SystemSnapshot",
    "create_default_catalog",
    "evaluate_initiative",
}


def test_public_api_is_explicit_and_exact() -> None:
    assert set(sirah.__all__) == EXPECTED_PUBLIC_API
    assert all(hasattr(sirah, name) for name in sirah.__all__)


def test_concrete_adapters_and_sdk_are_not_exported() -> None:
    excluded = {
        "FakeIntelligenceAdapter",
        "GeminiIntelligenceAdapter",
        "PiperSpeechOutput",
        "SimulatedRobotAdapter",
        "genai",
        "pydantic",
    }
    assert excluded.isdisjoint(sirah.__all__)


def test_distribution_metadata_configuration() -> None:
    with (Path(__file__).parents[1] / "pyproject.toml").open("rb") as source:
        project = load(source)["project"]
    assert project["name"] == "sirah"
    assert project["version"] == "0.1.0.dev0"
    assert project["requires-python"] == ">=3.13"
    assert project["dependencies"] == ["sirah-cortex==0.1.0a1"]
    assert project["optional-dependencies"]["gemini"] == [
        "google-genai",
        "pydantic",
    ]
    assert project["optional-dependencies"]["stt-vosk"] == [
        "vosk>=0.3.45,<0.4"
    ]
    assert project["license"] == "Apache-2.0"
    assert project["license-files"] == ["LICENSE"]


def test_base_facade_does_not_import_google_sdk() -> None:
    source = (Path(sirah.__file__).read_text(encoding="utf-8"))
    assert "google" not in source
    assert "pydantic" not in source


def test_gemini_adapter_has_no_robot_port_access() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "sirah" / "gemini.py"
    ).read_text(encoding="utf-8")
    imported_names = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "RobotPort" not in imported_names
    assert "RobotCommand" not in imported_names


def test_base_import_does_not_require_piper_or_audio_packages() -> None:
    source = Path(sirah.__file__).read_text(encoding="utf-8")
    assert "piper_speech" not in source
    assert "subprocess" not in source
    assert "vosk" not in source.casefold()


def test_isolated_import_is_lazy_and_starts_no_threads() -> None:
    script = """
import sys
import threading
before = {thread.ident for thread in threading.enumerate()}
import sirah
after_sirah = {thread.ident for thread in threading.enumerate()}
from sirah.piper_speech import PiperSpeechOutput
after_piper = {thread.ident for thread in threading.enumerate()}
assert "vosk" not in sys.modules
assert before == after_sirah == after_piper
assert PiperSpeechOutput.__name__ == "PiperSpeechOutput"
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 0, completed.stderr
