"""DiagnosticSnapshot/DiagnosticFace validation tests (M5.2B)."""

from __future__ import annotations

import dataclasses

import pytest

from sirah.perception.diagnostic import DiagnosticFace, DiagnosticSnapshot
from sirah.perception.evidence import StableEvent


def test_face_requires_normalized_box_and_confidence():
    DiagnosticFace(0.2, 0.2, 0.2, 0.2, 0.9)
    with pytest.raises(ValueError):
        DiagnosticFace(-0.1, 0.2, 0.2, 0.2, 0.9)
    with pytest.raises(ValueError):
        DiagnosticFace(0.2, 1.1, 0.2, 0.2, 0.9)
    with pytest.raises(ValueError):
        DiagnosticFace(0.2, 0.2, 0.2, 0.2, 1.5)


def test_snapshot_rejects_negative_index_and_bad_fps():
    DiagnosticSnapshot(frame_index=0, created_at=1.0, captured_at=1.0)
    with pytest.raises(ValueError):
        DiagnosticSnapshot(frame_index=-1, created_at=1.0, captured_at=1.0)
    with pytest.raises(ValueError):
        DiagnosticSnapshot(frame_index=0, created_at=1.0, captured_at=1.0, camera_fps=-1.0)


def test_event_ttl_elapsed_filters_by_observed_at():
    fresh = StableEvent("appear", "face", "face_appeared", 9.5, 0.9)
    old = StableEvent("appear", "hand", "hand_appeared", 7.0, 0.8)
    snapshot = DiagnosticSnapshot(
        frame_index=0, created_at=10.0, captured_at=10.0, events=(fresh, old)
    )
    assert snapshot.event_ttl_elapsed(now=10.0, ttl_s=2.0) == (fresh,)
    assert snapshot.event_ttl_elapsed(now=10.0, ttl_s=0.4) == ()
    assert snapshot.event_ttl_elapsed(now=12.0, ttl_s=2.0) == ()


def test_snapshot_is_frozen():
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=1.0, captured_at=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.camera_fps = 30.0  # type: ignore[misc]  # frozen dataclass