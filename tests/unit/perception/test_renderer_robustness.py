"""Renderer off-frame robustness tests (M5.2C).

A hand landmark outside [0, 1] (a hand entering/leaving the frame) is NOT
a pipeline failure. MediaPipe parity: finite off-frame points and non-finite
points have no drawable pixel and are skipped; connections are drawn only
when both endpoints are drawable. The renderer must never raise, never
mutate the source landmark/frame, and keep drawing the face + other hands.

A recording fake `cv2` is used to assert the exact draw policy without
brittle golden-pixel comparisons.
"""

from __future__ import annotations

import math

import numpy as np

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticFace, DiagnosticSnapshot
from sirah.perception.gesture import HandGesture, Landmark, RawHand
from sirah.perception.renderer import (
    DiagnosticRenderer,
    RenderContext,
    hand_pixel,
    raw_hand_label,
    stable_hand_label,
)

WIDTH, HEIGHT = 320, 240

HAND_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
)
EDGES_NOT_TOUCHING_WRIST = tuple((a, b) for a, b in HAND_EDGES if 0 not in (a, b))


def _hand(
    overrides: dict[int, tuple[float, float]] | None = None,
    *,
    handedness: str = "Right",
    category: str = "Open_Palm",
    index: int = 0,
) -> RawHand:
    """A full 21-landmark in-frame hand with optional per-index overrides.

    Defaults place every landmark in-frame so tests only count the effect
    of the overridden geometry.
    """
    landmarks = [Landmark(0.1 + 0.03 * i, 0.3, 0.0) for i in range(21)]
    for idx, (x, y) in (overrides or {}).items():
        landmarks[idx] = Landmark(x, y, 0.0)
    return RawHand(
        index=index,
        handedness=handedness,
        category=category,
        confidence=0.9,
        landmarks=tuple(landmarks),
    )


class FakeCV2:
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 1

    def __init__(self) -> None:
        self.lines: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self.circles: list[tuple[int, int]] = []
        self.texts: list[str] = []

    def line(self, out, p1, p2, color, thickness):
        self.lines.append((p1, p2))

    def circle(self, out, center, radius, color, thickness):
        self.circles.append(center)

    def putText(self, out, text, org, font, scale, color, thickness, line_type):
        self.texts.append(text)

    def getTextSize(self, text, font, scale, thickness):
        return (10 * len(text), 20)

    def rectangle(self, *args):
        pass


def _render_hand(
    raw: RawHand,
    renderer: DiagnosticRenderer | None = None,
    stable: HandGesture | None = None,
) -> tuple[FakeCV2, DiagnosticRenderer]:
    cv2_fake = FakeCV2()
    renderer = renderer or DiagnosticRenderer()
    from sirah.perception import renderer as renderer_mod

    out = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    renderer_mod._draw_hand(
        cv2_fake,
        out,
        raw,
        stable,
        WIDTH,
        HEIGHT,
        mirror=False,
        stale=False,
        now=0.0,
        frame_index=7,
        renderer=renderer,
    )
    return cv2_fake, renderer


def test_hand_pixel_exact_boundaries_and_valid_points():
    assert hand_pixel(0.0, 0.0, WIDTH, HEIGHT) == (0, 0)
    assert hand_pixel(1.0, 1.0, WIDTH, HEIGHT) == (WIDTH - 1, HEIGHT - 1)
    assert hand_pixel(0.5, 0.5, WIDTH, HEIGHT) == (round(0.5 * (WIDTH - 1)), round(0.5 * (HEIGHT - 1)))


def test_hand_pixel_slightly_outside_returns_none():
    assert hand_pixel(-0.001, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, -0.001, WIDTH, HEIGHT) is None
    assert hand_pixel(1.001, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, 1.001, WIDTH, HEIGHT) is None


def test_hand_pixel_moderately_outside_returns_none():
    assert hand_pixel(-0.2, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(1.2, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, -0.4, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, 1.5, WIDTH, HEIGHT) is None


def test_hand_pixel_nonfinite_returns_none():
    assert hand_pixel(math.nan, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, math.inf, WIDTH, HEIGHT) is None
    assert hand_pixel(-math.inf, 0.5, WIDTH, HEIGHT) is None
    assert hand_pixel(0.5, math.nan, WIDTH, HEIGHT) is None


def test_hand_pixel_mirror_reflects():
    assert hand_pixel(0.0, 0.5, WIDTH, HEIGHT, mirror=True)[0] == WIDTH - 1
    assert hand_pixel(1.0, 0.5, WIDTH, HEIGHT, mirror=True)[0] == 0


def test_hand_pixel_rejects_bad_dimensions():
    import pytest

    with pytest.raises(ValueError):
        hand_pixel(0.5, 0.5, 0, HEIGHT)
    with pytest.raises(ValueError):
        hand_pixel(0.5, 0.5, WIDTH, 0)


def test_all_in_frame_draws_points_edges_and_labels():
    raw = _hand()
    cv2_fake, _ = _render_hand(raw)
    assert len(cv2_fake.circles) == 21
    assert len(cv2_fake.lines) == len(HAND_EDGES)
    assert raw_hand_label(raw) in cv2_fake.texts


def test_slightly_outside_wrist_skipped_with_its_connections():
    raw = _hand({0: (0.2, -0.001)})  # wrist just off-frame
    cv2_fake, renderer = _render_hand(raw)
    assert renderer.out_of_bounds_landmarks == 1
    assert len(cv2_fake.circles) == 20  # wrist skipped, the rest draw
    # only edges not touching the wrist draw (MediaPipe parity)
    assert len(cv2_fake.lines) == len(EDGES_NOT_TOUCHING_WRIST)


def test_moderately_outside_points_skipped_but_valid_points_render():
    raw = _hand({0: (-0.2, 0.2), 2: (0.4, 1.2)})
    cv2_fake, renderer = _render_hand(raw)
    assert renderer.out_of_bounds_landmarks == 2
    assert len(cv2_fake.circles) == 19
    # 20 edges minus 5 touching the off-frame wrist minus (1,2)/(2,3)
    # touching the off-frame landmark 2
    assert len(cv2_fake.lines) == 13


def test_mixed_valid_invalid_axes_skip_and_count():
    raw = _hand({0: (0.5, -0.006), 1: (1.012, 0.5)})
    cv2_fake, renderer = _render_hand(raw)
    assert renderer.out_of_bounds_landmarks == 2
    assert len(cv2_fake.circles) == 19


def test_nonfinite_points_are_skipped_and_counted():
    raw = _hand({0: (math.nan, 0.2), 1: (0.3, math.inf)})
    cv2_fake, renderer = _render_hand(raw)
    assert renderer.nonfinite_landmarks == 2
    assert len(cv2_fake.circles) == 19
    assert renderer.out_of_bounds_landmarks == 0


def test_render_does_not_mutate_source_hand():
    raw = _hand({0: (math.nan, 0.2), 1: (-0.2, 0.2), 2: (0.3, 1.2)})
    original = (raw.landmarks[0].x, raw.landmarks[0].y, raw.landmarks[1].x, raw.landmarks[2].y)
    _render_hand(raw)
    after = (raw.landmarks[0].x, raw.landmarks[0].y, raw.landmarks[1].x, raw.landmarks[2].y)
    assert original == after


def test_render_does_not_mutate_source_frame():
    src = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    src[5, 5] = (1, 2, 3)
    raw = _hand({0: (-0.2, 0.2)})
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=0, payload=src, captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert np.array_equal(src, frame.payload)
    assert out is not frame.payload


def test_full_render_with_off_frame_hand_does_not_raise_and_keeps_face():
    raw = _hand({0: (-0.2, -0.1), 1: (1.1, 0.5), 2: (0.5, 1.3)})
    face = DiagnosticFace(0.3, 0.3, 0.2, 0.2, 0.9, attended=True)
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(
        frame_index=3,
        created_at=0.0,
        captured_at=0.0,
        faces=(face,),
        raw_hands=(raw,),
    )
    frame = Frame(index=3, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (HEIGHT, WIDTH, 3)  # face + camera frame still present
    assert renderer.out_of_bounds_landmarks == 3


def test_bad_hand_a_does_not_block_hand_b():
    bad = _hand({0: (math.nan, 0.5), 1: (-0.3, 0.5)}, handedness="Left", category="Closed_Fist")
    good = _hand(index=1)
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        raw_hands=(bad, good),
    )
    frame = Frame(index=0, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (HEIGHT, WIDTH, 3)
    assert renderer.nonfinite_landmarks == 1
    assert renderer.out_of_bounds_landmarks == 1


def test_two_in_frame_hands_render():
    left = _hand(handedness="Left", category="Open_Palm", index=0)
    right = _hand(handedness="Right", category="Victory", index=1)
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(
        frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(left, right)
    )
    frame = Frame(index=0, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0))
    assert out.shape == (HEIGHT, WIDTH, 3)
    assert renderer.out_of_bounds_landmarks == 0
    assert renderer.nonfinite_landmarks == 0


def test_mirror_path_with_off_frame_geometry_does_not_raise():
    raw = _hand({0: (-0.001, 0.2)})
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=0, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    out = renderer.render(frame, snapshot, RenderContext(now=0.0, mirror=True))
    assert out.shape == (HEIGHT, WIDTH, 3)
    assert renderer.out_of_bounds_landmarks == 1


def test_labels_anchor_at_wrist_when_drawable():
    raw = _hand()  # wrist (landmark 0) in frame
    stable = HandGesture("thumb_up", 0.9, "Right", raw.index)
    cv2_fake, _ = _render_hand(raw, renderer=DiagnosticRenderer(), stable=stable)
    assert stable_hand_label(stable) in cv2_fake.texts
    assert raw_hand_label(raw) in cv2_fake.texts


def test_labels_skipped_when_wrist_undrawable():
    raw = _hand({0: (0.5, -0.2)})  # wrist off-frame
    cv2_fake, renderer = _render_hand(raw)
    assert renderer.out_of_bounds_landmarks == 1
    assert raw_hand_label(raw) not in cv2_fake.texts  # no anchor -> no label


def test_anomaly_first_occurrence_logged_with_full_context(caplog):
    import logging

    raw = _hand({0: (math.nan, 0.2)})
    renderer = DiagnosticRenderer()
    snapshot = DiagnosticSnapshot(frame_index=42, created_at=0.0, captured_at=0.0, raw_hands=(raw,))
    frame = Frame(index=42, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    with caplog.at_level(logging.WARNING, logger="sirah.perception.renderer"):
        renderer.render(frame, snapshot, RenderContext(now=0.0))
    messages = [r.getMessage() for r in caplog.records if r.name == "sirah.perception.renderer"]
    assert any("frame=42" in m and "landmark=0" in m and "hand_idx=0" in m and "x=nan" in m for m in messages)
    assert renderer.nonfinite_landmarks == 1


def test_repeated_anomaly_log_is_rate_limited(caplog):
    import logging

    renderer = DiagnosticRenderer()
    frame = Frame(index=1, payload=np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), captured_at=0.0)
    with caplog.at_level(logging.WARNING, logger="sirah.perception.renderer"):
        for i in range(5):
            raw = _hand({0: (math.nan, 0.2)})
            s = DiagnosticSnapshot(frame_index=i, created_at=0.0 + i * 0.5, captured_at=0.0, raw_hands=(raw,))
            renderer.render(frame, s, RenderContext(now=0.0 + i * 0.5))
    records = [r for r in caplog.records if r.name == "sirah.perception.renderer"]
    # exactly one first-occurrence detail log + one rate-limited summary,
    # never one log per frame
    assert len(records) == 2
    assert "skipped: frame=0" in records[0].getMessage()
    assert "more (total 2" in records[1].getMessage()
    assert renderer.nonfinite_landmarks == 5