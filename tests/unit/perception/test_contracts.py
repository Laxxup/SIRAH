"""Perception contracts tests (Stage 8): nominal Protocols type-check the
wiring; GazeTarget/Frame carry the A1 world semantics."""

from __future__ import annotations

from sirah.behavior.contracts import Behavior
from sirah.behavior.gaze_behavior import GazeBehavior
from sirah.perception.contracts import (
    CameraSource,
    FaceDetector,
    Frame,
    GazeTarget,
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

    assert isinstance(FakeCamera(), CameraSource)
    assert isinstance(FakeDetector(), FaceDetector)
    assert isinstance(GazeBehavior(), Behavior)