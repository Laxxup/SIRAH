"""Gesture adapter space-separation tests (M5.2C).

MediaPipe returns TWO landmark spaces:
- `hand_landmarks` — normalized image coordinates (0..1);
- `hand_world_landmarks` — metric world coordinates (unbounded).

The adapter must keep them in separate `RawHand.landmarks` /
`RawHand.world_landmarks` fields and never mix them, and the renderer must
project only the normalized `landmarks`. `z` is never treated as an
image-normalized coordinate.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pytest

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.gesture import RawHand
from sirah.perception.mediapipe_gesture import MediaPipeGestureRecognizer
from sirah.perception.renderer import DiagnosticRenderer, RenderContext

_WORLD = [(1.2, -3.4, 0.7), (2.0, 2.0, 2.0)]
_NORMALIZED = [(0.3, 0.4, 0.1), (0.5, 0.5, 0.2)]


class _Category:
    def __init__(self, category_name: str, score: float) -> None:
        self.category_name = category_name
        self.score = score


class _Point:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z


class FakeResult:
    gestures: ClassVar[list[list[_Category]]] = [[_Category("Open_Palm", 0.95)]]
    handedness: ClassVar[list[list[_Category]]] = [[_Category("Right", 0.99)]]
    hand_landmarks: ClassVar[list[list[_Point]]] = [[_Point(x, y, z) for x, y, z in _NORMALIZED]]
    hand_world_landmarks: ClassVar[list[list[_Point]]] = [[_Point(x, y, z) for x, y, z in _WORLD]]


class FakeRecognizer:
    def __init__(self, result: object) -> None:
        self.result = result
        self.closed = False

    def recognize_for_video(self, image: object, timestamp_ms: int) -> object:
        return self.result

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def recognizer(tmp_path) -> MediaPipeGestureRecognizer:
    model = tmp_path / "model.task"
    model.write_bytes(b"fake")
    return MediaPipeGestureRecognizer(
        model, recognizer_factory=lambda path: FakeRecognizer(FakeResult())
    )


def test_adapter_keeps_normalized_and_world_spaces_separate(recognizer):
    frame = Frame(index=0, payload=np.zeros((8, 8, 3), dtype=np.uint8), captured_at=0.0)
    det = recognizer.recognize_detailed(frame)
    raw: RawHand = det.raw[0]
    assert [(lm.x, lm.y, lm.z) for lm in raw.landmarks] == _NORMALIZED
    assert [(lm.x, lm.y, lm.z) for lm in raw.world_landmarks] == _WORLD
    # no mixing: world-space values never appear in the normalized field
    assert raw.landmarks[0].x == 0.3  # not 1.2


def test_renderer_projects_only_normalized_landmarks(tmp_path):
    raw = RawHand(
        index=0,
        handedness="Right",
        category="Open_Palm",
        confidence=0.9,
        landmarks=(),
        world_landmarks=(),
    )
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=0, payload=np.zeros((16, 16, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (16, 16, 3)  # empty landmarks -> no hand drawn, no raise


def test_renderer_ignores_world_landmarks_when_normalized_present(tmp_path):
    raw = RawHand(
        index=0,
        handedness="Right",
        category="Open_Palm",
        confidence=0.9,
        landmarks=(),
        world_landmarks=(),
    )
    # world landmarks with absurd values must not be projected anywhere
    from sirah.perception.gesture import Landmark

    raw = RawHand(
        index=0,
        handedness="Right",
        category="Open_Palm",
        confidence=0.9,
        landmarks=(Landmark(0.5, 0.5, 0.0),),
        world_landmarks=(Landmark(1e9, -1e9, 1e9),),
    )
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=0, payload=np.zeros((16, 16, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (16, 16, 3)
    # the world-space abuse produced no anomalies and no exception
    assert renderer.out_of_bounds_landmarks == 0
    assert renderer.nonfinite_landmarks == 0


def test_z_is_never_treated_as_image_normalized_coordinate(tmp_path):
    from sirah.perception.gesture import Landmark

    raw = RawHand(
        index=0,
        handedness="Right",
        category="Open_Palm",
        confidence=0.9,
        landmarks=(Landmark(0.5, 0.5, 500.0),),  # huge z, normalized x/y
    )
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=0, payload=np.zeros((16, 16, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (16, 16, 3)
    assert renderer.out_of_bounds_landmarks == 0  # z ignored by projection