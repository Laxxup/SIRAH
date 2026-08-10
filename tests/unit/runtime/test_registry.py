"""Runtime registry tests (Stage 7)."""

from __future__ import annotations

from sirah.runtime.registry import ComponentRegistry, ComponentState, ComponentStatus


def test_fresh_registry_reports_off():
    reg = ComponentRegistry()
    assert reg.get("eyes") == ComponentState(ComponentStatus.OFF)


def test_set_and_snapshot():
    reg = ComponentRegistry()
    reg.set("eyes", ComponentStatus.READY, "linked")
    reg.set("camera", ComponentStatus.DEGRADED, "frame error")
    assert reg.snapshot() == {
        "eyes": ComponentState(ComponentStatus.READY, "linked"),
        "camera": ComponentState(ComponentStatus.DEGRADED, "frame error"),
    }


def test_update_preserves_unchanged_fields():
    reg = ComponentRegistry()
    reg.set("eyes", ComponentStatus.READY, "linked")
    reg.update("eyes", status=ComponentStatus.DEGRADED)
    state = reg.get("eyes")
    assert state.status == ComponentStatus.DEGRADED
    assert state.detail == "linked"


def test_all_ready_requires_at_least_one_ready():
    reg = ComponentRegistry()
    assert not reg.all_ready()
    reg.set("lab", ComponentStatus.OFF)
    reg.set("eyes", ComponentStatus.DEGRADED)
    assert not reg.all_ready()
    reg.set("camera", ComponentStatus.READY)
    assert reg.all_ready()