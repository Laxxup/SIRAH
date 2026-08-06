"""Test factory and system assembly."""

from __future__ import annotations

from sirah.factory import SystemAssembly, SystemProfile, build_system


def test_build_system_dev_laptop() -> None:
    sys = build_system(profile=SystemProfile.DEV_LAPTOP)
    assert isinstance(sys, SystemAssembly)
    assert sys.orchestrator is not None
    assert sys.situational is not None
    assert sys.intelligence is not None
    assert sys.capabilities is not None
    assert sys.runner is not None
    assert sys.registry is not None
    assert sys.bridge is None


def test_build_system_with_groq() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="groq",
        groq_api_key=None,
    )
    assert sys.intelligence is not None


def test_build_system_with_laboratory() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="laboratory",
    )
    assert sys.intelligence is not None


def test_build_system_with_scripted() -> None:
    sys = build_system(
        profile=SystemProfile.DEV_LAPTOP,
        intelligence_type="scripted",
    )
    assert sys.intelligence is not None


def test_build_system_distributed_has_bridge() -> None:
    sys = build_system(profile=SystemProfile.DEV_DISTRIBUTED)
    assert sys.bridge is not None
