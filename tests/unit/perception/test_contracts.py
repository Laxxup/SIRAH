"""Perception contracts tests (Stage 8): nominal Protocols type-check the
wiring; GazeTarget/Frame carry the A1 world semantics."""

from __future__ import annotations

from sirah.behavior.contracts import Behavior
from sirah.behavior.event_detector import EventDetector
from sirah.behavior.gaze_behavior import GazeBehavior
from sirah.perception.contracts import (
    CameraSource,
    FaceDetector,
    Frame,
    GazeTarget,
    MultiFaceDetector,
    PerceptionSnapshot,
    snapshot_from_target,
)


def test_gaze_target_defaults_to_full_confidence():
    assert GazeTarget(0.5, -0.1).confidence == 1.0


def test_frame_carries_index_and_opaque_payload():
    frame = Frame(index=3)
    assert frame.index == 3
    assert frame.payload is None


def test_isinstance_checks_against_nominal_protocols():
    class FakeCamera:
        async def start(self) -> None: ...

        async def next_frame(self) -> Frame | None:
            return None

        async def stop(self) -> None: ...

    class FakeDetector:
        def detect(self, frame: Frame) -> GazeTarget | None:
            return None

    class FakeMultiDetector:
        def detect_many(self, frame: Frame):
            return []

    assert isinstance(FakeCamera(), CameraSource)
    assert isinstance(FakeDetector(), FaceDetector)
    assert isinstance(FakeMultiDetector(), MultiFaceDetector)
    assert isinstance(GazeBehavior(), Behavior)


def test_snapshot_from_target_is_tracking():
    snapshot = snapshot_from_target(GazeTarget(0.2, -0.3, 0.8), observed_at=1.0)
    assert snapshot == PerceptionSnapshot(1.0, True, 0.2, -0.3, 0.8, "tracking")


def test_snapshot_from_absence_preserves_semantic_state():
    snapshot = snapshot_from_target(None, observed_at=2.0, absent_state="lost")
    assert snapshot == PerceptionSnapshot(2.0, False, None, None, None, "lost")


def test_snapshot_rejects_inconsistent_tracking_values():
    import pytest

    with pytest.raises(ValueError, match="tracking"):
        PerceptionSnapshot(1.0, True, None, None, None, "tracking")


def test_snapshot_satisfies_behavior_event_detector_protocol():
    detector = EventDetector(arrival_samples=1, cooldown_s=0.0)
    event = detector.observe(snapshot_from_target(GazeTarget(0.0, 0.0), observed_at=1.0))
    assert event is not None
    assert event.kind.value == "person_arrived"
