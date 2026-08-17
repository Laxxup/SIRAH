"""WorldState tests (M9): snapshot semantics, validation and builder."""

from __future__ import annotations

import pytest

from sirah.perception.contracts import GazeTarget
from sirah.perception.world_state import WorldState, WorldStateBuilder


def _target(x: float = 0.2, y: float = -0.3, conf: float = 0.9) -> GazeTarget:
    return GazeTarget(x, y, conf)


def test_present_state_carries_target_and_freshness():
    state = WorldState(
        face_present=True,
        primary_target=_target(),
        last_observed_at=10.0,
        target_age_s=0.5,
        gaze_x=0.2,
        gaze_y=-0.3,
        gaze_producer="face_tracking",
        vision_degraded=False,
        observed_at=10.5,
    )
    assert state.face_present
    assert state.primary_target == _target()
    assert state.target_age_s == 0.5
    assert state.gaze_producer == "face_tracking"


def test_absent_state_requires_no_target_or_gaze():
    state = WorldState(
        face_present=False,
        primary_target=None,
        last_observed_at=None,
        target_age_s=None,
        gaze_x=None,
        gaze_y=None,
        gaze_producer=None,
        vision_degraded=True,
        observed_at=11.0,
    )
    assert not state.face_present
    assert state.vision_degraded


def test_present_state_rejects_missing_target():
    with pytest.raises(ValueError, match="face_present"):
        WorldState(
            face_present=True,
            primary_target=None,
            last_observed_at=10.0,
            target_age_s=0.5,
            gaze_x=None,
            gaze_y=None,
            gaze_producer=None,
            vision_degraded=False,
            observed_at=10.5,
        )


def test_absent_state_rejects_stale_target():
    with pytest.raises(ValueError, match="no face"):
        WorldState(
            face_present=False,
            primary_target=_target(),
            last_observed_at=10.0,
            target_age_s=2.0,
            gaze_x=None,
            gaze_y=None,
            gaze_producer=None,
            vision_degraded=False,
            observed_at=12.0,
        )


def test_gaze_setpoint_requires_all_fields():
    with pytest.raises(ValueError, match="gaze"):
        WorldState(
            face_present=False,
            primary_target=None,
            last_observed_at=None,
            target_age_s=None,
            gaze_x=0.1,
            gaze_y=None,
            gaze_producer=None,
            vision_degraded=False,
            observed_at=10.0,
        )


def test_out_of_range_gaze_rejected():
    with pytest.raises(ValueError, match="normalized"):
        WorldState(
            face_present=True,
            primary_target=_target(),
            last_observed_at=10.0,
            target_age_s=0.0,
            gaze_x=1.5,
            gaze_y=0.0,
            gaze_producer="face_tracking",
            vision_degraded=False,
            observed_at=10.0,
        )


def test_builder_tracks_freshness_across_ticks():
    builder = WorldStateBuilder()
    builder.observe(_target(), now=10.0)
    state = builder.snapshot(
        now=10.5,
        gaze_x=0.2,
        gaze_y=-0.3,
        gaze_producer="face_tracking",
        vision_degraded=False,
    )
    assert state.face_present
    assert state.target_age_s == 0.5

    builder.observe(None, now=10.6)
    state = builder.snapshot(
        now=12.0,
        gaze_x=None,
        gaze_y=None,
        gaze_producer=None,
        vision_degraded=False,
    )
    assert not state.face_present
    assert state.primary_target is None
    assert state.target_age_s == pytest.approx(2.0)  # last seen 2 s ago


def test_builder_never_presents_before_any_detection():
    builder = WorldStateBuilder()
    state = builder.snapshot(
        now=1.0,
        gaze_x=None,
        gaze_y=None,
        gaze_producer=None,
        vision_degraded=False,
    )
    assert not state.face_present
    assert state.last_observed_at is None
    assert state.target_age_s is None


def test_builder_requires_finite_clock():
    builder = WorldStateBuilder()
    with pytest.raises(ValueError):
        builder.observe(_target(), now=float("nan"))