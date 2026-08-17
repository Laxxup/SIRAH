"""WorldState tests (M9): snapshot semantics, validation and builder."""

from __future__ import annotations

import pytest

from sirah.perception.contracts import GazeTarget
from sirah.perception.world_state import PerceptionFacts, WorldState, WorldStateBuilder


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


# ---------------------------------------------------------------------------
# PerceptionFacts freshness (M3): stale perception is never current truth
# ---------------------------------------------------------------------------


def _facts():
    from sirah.perception.evidence import EvidenceHub, RawObservation

    hub = EvidenceHub(confirm_samples=1)
    hub.observe(
        [
            RawObservation("yunet", "person", "present", 0.9, 0.0),
            RawObservation("gesture", "gesture", "thumb_up", 0.9, 0.0),
        ],
        now=0.0,
    )
    return PerceptionFacts.from_snapshot(
        hub.observe([], now=0.0), observed_at=0.0
    )


def test_perception_facts_carry_temporal_validity():
    facts = _facts()
    person = facts.state_of("person")
    assert person is not None
    assert person.value == "present"
    assert person.observed_at == 0.0
    assert person.confirmed_at == 0.0
    assert person.expires_at is not None  # TTL set by the hub default


def test_fresh_facts_are_fresh_and_stale_facts_are_filtered():
    facts = _facts()
    assert facts.fresh_state_of("person", now=0.5) is not None  # within TTL
    assert facts.fresh_state_of("person", now=5.0) is None  # TTL (3s) lapsed
    assert facts.fresh(0.5).state_of("person") is not None
    assert facts.fresh(5.0).state_of("person") is None
    assert facts.stale(5.0) == facts.states  # everything stale later


def test_stale_perception_never_surfaces_as_current_truth():
    facts = _facts()
    assert facts.fresh_state_of("gesture", now=0.1) is not None
    assert facts.fresh_state_of("gesture", now=4.0) is None


def test_world_state_carries_fresh_perception_facts():
    facts = _facts()
    state = WorldState(
        face_present=True,
        primary_target=_target(),
        last_observed_at=10.0,
        target_age_s=0.0,
        gaze_x=0.2,
        gaze_y=-0.3,
        gaze_producer="face_tracking",
        vision_degraded=False,
        observed_at=10.0,
        perception=facts,
    )
    assert state.perception is not None
    assert state.perception.state_of("person").value == "present"  # type: ignore[union-attr]


def test_world_state_without_perception_stays_backwards_compatible():
    state = WorldState(
        face_present=False,
        primary_target=None,
        last_observed_at=None,
        target_age_s=None,
        gaze_x=None,
        gaze_y=None,
        gaze_producer=None,
        vision_degraded=False,
        observed_at=10.0,
    )
    assert state.perception is None