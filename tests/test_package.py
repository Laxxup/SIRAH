"""Fachada pública y metadata de la distribución pre-alpha."""

import ast
from pathlib import Path
from tomllib import load

import sirah


EXPECTED_PUBLIC_API = {
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
    "SessionContextStore",
    "SituationalCoordinator",
    "SirahApplicationError",
    "SpeechOutputPort",
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
