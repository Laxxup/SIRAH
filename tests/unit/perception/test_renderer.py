"""Diagnostic renderer tests (M5.2B): pure, deterministic, headless-safe.

The renderer must render synthetic/replay/deterministic results without a
display server, never mutate the shared broker frame, and never import
MediaPipe internals. Geometry assertions cover projection and mirroring;
pixel-content assertions are deliberately avoided (no brittle golden-pixel
or font-snapshot tests).
"""

from __future__ import annotations

import numpy as np
import pytest

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticFace, DiagnosticSnapshot
from sirah.perception.gesture import HandGesture, Landmark, RawHand
from sirah.perception.renderer import (
    DiagnosticRenderer,
    RenderContext,
    project_x,
    project_y,
    raw_hand_label,
    stable_hand_label,
)


def _frame(width: int = 320, height: int = 240) -> Frame:
    return Frame(index=1, payload=np.zeros((height, width, 3), dtype=np.uint8), captured_at=1.0)


def _snapshot(*, now: float = 10.0, **kwargs) -> DiagnosticSnapshot:
    defaults = {"frame_index": 1, "created_at": 9.9, "captured_at": 9.8}
    defaults.update(kwargs)
    return DiagnosticSnapshot(**defaults)


def _raw_hand() -> RawHand:
    landmarks = tuple(
        Landmark(0.1 + 0.01 * i, 0.1 + 0.01 * i, 0.0) for i in range(21)
    )
    return RawHand(index=0, handedness="Right", category="Closed_Fist", confidence=0.8, landmarks=landmarks)


def _stable_hand() -> HandGesture:
    return HandGesture("thumb_up", 0.9, "Right", 0)


def test_project_x_and_y_are_identity_at_edges():
    assert project_x(0.0, 320) == 0
    assert project_x(1.0, 320) == 319
    assert project_y(0.0, 240) == 0
    assert project_y(1.0, 240) == 239


def test_project_x_mirror_reflects_about_center():
    assert project_x(0.0, 320, mirror=True) == 319
    assert project_x(1.0, 320, mirror=True) == 0
    assert project_x(0.5, 320, mirror=True) == project_x(0.5, 320)


def test_render_never_mutates_the_shared_frame():
    src = np.zeros((240, 320, 3), dtype=np.uint8)
    src[10, 10] = (1, 2, 3)
    frame = Frame(index=1, payload=src, captured_at=1.0)
    snapshot = _snapshot(faces=(DiagnosticFace(0.2, 0.2, 0.2, 0.2, 0.9, True),))
    out = DiagnosticRenderer().render(frame, snapshot, RenderContext(now=10.0))
    assert np.array_equal(src, frame.payload)  # source unchanged
    assert out is not frame.payload  # a copy, not a view


def test_render_returns_usable_image_for_detection_data():
    snapshot = _snapshot(
        faces=(DiagnosticFace(0.2, 0.2, 0.2, 0.2, 0.9, True),),
        raw_hands=(_raw_hand(),),
        hands=(_stable_hand(),),
    )
    out = DiagnosticRenderer().render(_frame(), snapshot, RenderContext(now=10.0))
    assert out.shape == (240, 320, 3)
    assert out.dtype == np.uint8


def test_render_without_snapshot_draws_hud_only():
    out = DiagnosticRenderer().render(_frame(), None, RenderContext(now=10.0))
    assert out.shape == (240, 320, 3)


def test_render_drops_overlays_older_than_drop_window():
    renderer = DiagnosticRenderer()
    snapshot = _snapshot(faces=(DiagnosticFace(0.2, 0.2, 0.2, 0.2, 0.9, True),))
    out = renderer.render(_frame(), snapshot, RenderContext(now=10.0))
    assert out.shape == (240, 320, 3)  # drawn, no exception
    # an overlay 5s old exceeds the 1s drop window; still a valid image
    old = _snapshot(now=10.0, created_at=5.0)
    out_old = renderer.render(_frame(), old, RenderContext(now=10.0))
    assert out_old.shape == (240, 320, 3)


def test_mirror_transform_propagates_to_projection():
    face = DiagnosticFace(0.1, 0.1, 0.2, 0.2, 0.9, True)
    mirror = project_x(face.x, 320, mirror=True)
    assert mirror == project_x(0.9, 320)


def test_raw_and_stable_labels_are_distinct():
    raw = raw_hand_label(_raw_hand())
    stable = stable_hand_label(_stable_hand())
    assert "Closed_Fist" in raw  # raw MediaPipe category
    assert "thumb_up" in stable  # allowlisted SIRAH value
    assert raw != stable


def test_renderer_parameter_validation():
    with pytest.raises(ValueError):
        DiagnosticRenderer(stale_after_s=0.0)
    with pytest.raises(ValueError):
        DiagnosticRenderer(stale_after_s=2.0, drop_after_s=1.0)
    with pytest.raises(ValueError):
        project_x(1.5, 320)
    with pytest.raises(ValueError):
        project_y(0.5, 0)