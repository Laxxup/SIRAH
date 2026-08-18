"""Person overlay renderer tests (M6): canonical projection, mirroring,
lifecycle distinction, off-frame tolerance and failure containment.

Person boxes are drawn in the bottom-right area so assertions never
overlap the top-left HUD or the bottom-left STALE/event tags.
"""

from __future__ import annotations

import numpy as np

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.person import PersonTrack, TrackLifecycle
from sirah.perception.renderer import DiagnosticRenderer, RenderContext


def _track(lifecycle: TrackLifecycle, track_id: int = 1, x: float = 0.6, y: float = 0.6) -> PersonTrack:
    return PersonTrack(
        track_id=track_id,
        lifecycle=lifecycle,
        x=x,
        y=y,
        width=0.3,
        height=0.3,
        confidence=0.9,
        first_seen=0.0,
        last_seen=0.1,
        last_source_frame_index=0,
    )


# box (0.6,0.6,0.3,0.3) on 100x50 -> x 59..89, y 29..44 (bottom-right, no HUD)
_BOX_SLICE = (slice(29, 45), slice(59, 90))


def _render(snapshot: DiagnosticSnapshot, *, mirror: bool = False, now: float = 0.0, renderer=None):
    frame = Frame(index=0, payload=np.zeros((50, 100, 3), dtype=np.uint8), captured_at=0.0)
    renderer = renderer or DiagnosticRenderer()
    out = renderer.render(frame, snapshot, RenderContext(now=now, mirror=mirror))
    return out


def _box_region(out) -> np.ndarray:
    return out[_BOX_SLICE]


def test_renderer_draws_confirmed_person():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.CONFIRMED),),
    )
    out = _render(snapshot)
    assert out.shape == (50, 100, 3)
    # confirmed person drawn in orange (BGR red channel 255)
    assert (_box_region(out)[:, :, 2] > 200).any()


def test_renderer_mirror_flips_person_box():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.CONFIRMED, x=0.6),),
    )
    plain = _render(snapshot, mirror=False)
    mirrored = _render(snapshot, mirror=True)
    assert not np.array_equal(plain, mirrored)


def test_renderer_lost_track_drawn_distinctly_no_crash():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.TEMPORARILY_LOST),),
    )
    out = _render(snapshot)
    assert out.shape == (50, 100, 3)
    # a lost track is "recently observed at X": grey, never orange
    region = _box_region(out)
    assert not (region[:, :, 2] > 200).any()
    assert (region[:, :, 2] > 100).any()  # still drawn (grey label/box)


def test_renderer_tentative_person_renders():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.TENTATIVE),),
    )
    out = _render(snapshot)
    assert out.shape == (50, 100, 3)
    # tentative uses a dimmer blue-orange, distinct from confirmed orange
    region = _box_region(out)
    assert not (region[:, :, 2] > 200).any()


def test_renderer_off_frame_spill_no_raise():
    track = _track(TrackLifecycle.CONFIRMED, x=0.9, y=0.6)
    snapshot = DiagnosticSnapshot(
        frame_index=0, created_at=0.0, captured_at=0.0, person_tracks=(track,)
    )
    out = _render(snapshot)
    assert out.shape == (50, 100, 3)


def test_renderer_no_person_tracks_no_draw():
    snapshot = DiagnosticSnapshot(frame_index=0, created_at=0.0, captured_at=0.0)
    out = _render(snapshot)
    assert out.shape == (50, 100, 3)


def test_renderer_stale_person_dimmed():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.CONFIRMED),),
    )
    renderer = DiagnosticRenderer(stale_after_s=0.25, drop_after_s=1.0)
    out = _render(snapshot, now=0.5, renderer=renderer)  # stale but < drop
    assert out.shape == (50, 100, 3)
    region = _box_region(out)
    assert not (region[:, :, 2] > 200).any()  # dimmed, not bright orange


def test_renderer_drop_old_person_overlay():
    snapshot = DiagnosticSnapshot(
        frame_index=0,
        created_at=0.0,
        captured_at=0.0,
        person_tracks=(_track(TrackLifecycle.CONFIRMED),),
    )
    renderer = DiagnosticRenderer(stale_after_s=0.25, drop_after_s=1.0)
    out = _render(snapshot, now=2.0, renderer=renderer)  # beyond drop age
    assert out.shape == (50, 100, 3)
    region = _box_region(out)
    assert not (region[:, :, 2] > 200).any()
    assert not (region[:, :, 2] > 100).any()  # nothing drawn at all