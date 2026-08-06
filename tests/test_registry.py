"""Test ComponentRegistry."""

from __future__ import annotations

from sirah.core.registry import ComponentRegistry
from sirah.types import (
    ComponentKind,
    ComponentStatus,
    ConversationMessage,
    ConversationResult,
)


def test_registry_register() -> None:
    reg = ComponentRegistry()
    cid = reg.register(ComponentKind.CORE, "test")
    assert cid.kind == ComponentKind.CORE
    assert cid.name == "test"


def test_registry_update_status() -> None:
    reg = ComponentRegistry()
    cid = reg.register(ComponentKind.VOICE, "tts")
    reg.update(cid, ComponentStatus.READY, "ok")
    assert reg.component_status(cid) == ComponentStatus.READY


def test_registry_snapshot() -> None:
    reg = ComponentRegistry()
    reg.register(ComponentKind.CORE, "test")
    snap = reg.snapshot()
    assert snap.healthy()
    assert len(snap.components) == 1


def test_registry_record_results() -> None:
    reg = ComponentRegistry()
    msg = ConversationMessage(role="assistant", content="ok")
    result = ConversationResult(message=msg)
    reg.record_result(result)
    results = reg.last_results
    assert len(results) == 1
    assert results[0].message.content == "ok"
