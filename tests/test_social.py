"""Test initiative and social memory."""

from __future__ import annotations

from sirah.social.initiative import evaluate_initiative
from sirah.social.memory import InteractionMemory
from sirah.types import (
    FaceDetection,
    InitiativeAction,
    PerceptionFrame,
)


def test_memory_record_entries() -> None:
    m = InteractionMemory(max_entries=5)
    for i in range(10):
        m.record(f"event {i}")
    assert len(m.entries) <= 5


def test_memory_greet_cooldown() -> None:
    m = InteractionMemory(cooldown_s=30.0)
    assert m.can_greet
    m.mark_greet()
    assert not m.can_greet


def test_initiative_no_faces() -> None:
    frame = PerceptionFrame(timestamp=0)
    mem = InteractionMemory()
    d = evaluate_initiative(frame, mem)
    assert d.action == InitiativeAction.SILENT


def test_initiative_first_greet() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    frame = PerceptionFrame(timestamp=0, faces=(face,))
    mem = InteractionMemory()
    d = evaluate_initiative(frame, mem)
    assert d.action == InitiativeAction.GREET
    assert "Hola" in d.text


def test_initiative_returning_person() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.8)
    frame = PerceptionFrame(timestamp=0, faces=(face,))
    mem = InteractionMemory(cooldown_s=0.0)
    mem.mark_greet()
    mem.record("previous interaction")
    d = evaluate_initiative(frame, mem)
    assert d.action == InitiativeAction.CHECK_IN


def test_initiative_active_conversation_silent() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    frame = PerceptionFrame(timestamp=0, faces=(face,))
    mem = InteractionMemory()
    d = evaluate_initiative(frame, mem, active_conversation=True)
    assert d.action == InitiativeAction.SILENT


def test_initiative_cooldown_silent() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    frame = PerceptionFrame(timestamp=0, faces=(face,))
    mem = InteractionMemory()
    mem.mark_greet()
    d = evaluate_initiative(frame, mem)
    assert d.action == InitiativeAction.SILENT
