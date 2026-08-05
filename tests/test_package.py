"""Public API integrity and package metadata."""

from __future__ import annotations

import sirah


def test_package_imports() -> None:
    assert sirah.__all__ is not None


def test_build_system_in_all() -> None:
    assert "build_system" in sirah.__all__


def test_system_profile_in_all() -> None:
    assert "SystemProfile" in sirah.__all__


def test_system_assembly_in_all() -> None:
    assert "SystemAssembly" in sirah.__all__


def test_key_classes_in_namespace() -> None:
    names = dir(sirah)
    assert "SirahOrchestrator" in names
    assert "ConversationContext" in names
    assert "ComponentRegistry" in names
    assert "CapabilityCatalog" in names
    assert "CapabilityPolicy" in names
    assert "ActionRunner" in names
    assert "SituationalCoordinator" in names
    assert "InteractionMemory" in names
    assert "evaluate_initiative" in names


def test_key_errors_in_namespace() -> None:
    names = dir(sirah)
    assert "SirahError" in names
    assert "SirahFatalError" in names
    assert "SirahRecoverableError" in names
    assert "IntelligenceError" in names
    assert "PerceptionError" in names
    assert "SpeechError" in names
    assert "ActionError" in names
    assert "BridgeError" in names
