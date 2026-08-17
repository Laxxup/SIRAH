"""Evidence layer tests (M2): confirmation, rejection, TTL, hysteresis,
cooldown, stale state and state/event semantics."""

from __future__ import annotations

import math

import pytest

from sirah.perception.evidence import (
    EvidenceFilter,
    EvidenceHub,
    RawObservation,
    RejectionReason,
)


def _raw(
    value: str,
    confidence: float,
    *,
    observed_at: float,
    source: str = "gesture",
    kind: str = "gesture",
    track_id: str | None = None,
) -> RawObservation:
    return RawObservation(source, kind, value, confidence, observed_at, track_id)


# ---------------------------------------------------------------------------
# Confirmation / rejection
# ---------------------------------------------------------------------------


def test_confirms_after_two_consecutive_observations():
    filt = EvidenceFilter("gesture", confirm_samples=2)
    first = filt.observe(_raw("thumb_up", 0.94, observed_at=0.0), now=0.0)
    assert first.state is None
    assert first.pending is not None and first.pending.confirm_count == 1
    second = filt.observe(_raw("thumb_up", 0.91, observed_at=0.1), now=0.1)
    assert second.state is not None and second.state.value == "thumb_up"
    assert second.events[0].event == "gesture_thumb_up_confirmed"
    assert len(second.events) == 1


def test_holding_gesture_emits_no_duplicate_events():
    filt = EvidenceFilter("gesture", confirm_samples=2)
    events = []
    for t, conf in ((0.0, 0.94), (0.1, 0.91), (0.2, 0.93), (0.3, 0.9)):
        update = filt.observe(_raw("thumb_up", conf, observed_at=t), now=t)
        events.extend(update.events)
    assert len(events) == 1
    assert events[0].event == "gesture_thumb_up_confirmed"


def test_noisy_weak_observations_never_confirm():
    filt = EvidenceFilter("gesture", confirm_samples=2, min_confidence=0.6)
    for t, value, conf in ((0.0, "thumb_up", 0.55), (0.1, "thumb_up", 0.4), (0.2, "victory", 0.49)):
        update = filt.observe(_raw(value, conf, observed_at=t), now=t)
        assert update.state is None
    assert not [e for e in filt.observe(_raw("thumb_up", 0.55, observed_at=0.3), now=0.3).events]


def test_below_confidence_is_reported_for_diagnostics():
    filt = EvidenceFilter("gesture", min_confidence=0.6)
    raw = _raw("thumb_up", 0.4, observed_at=0.0)
    update = filt.observe(raw, now=0.0)
    assert update.state is None
    assert len(update.rejected) == 1
    assert update.rejected[0].reason == RejectionReason.BELOW_CONFIDENCE
    assert update.rejected[0].raw is raw


def test_confirm_window_resets_stale_confirmation():
    filt = EvidenceFilter("gesture", confirm_samples=3, confirm_window_s=0.5)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.0), now=0.0)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.1), now=0.1)
    # confirmation lapsed: restart count, so no promotion yet
    update = filt.observe(_raw("thumb_up", 0.9, observed_at=1.0), now=1.0)
    assert update.state is None
    assert update.pending is not None and update.pending.confirm_count == 1


# ---------------------------------------------------------------------------
# State/event semantics
# ---------------------------------------------------------------------------


def test_release_emits_single_released_event_after_grace():
    filt = EvidenceFilter("gesture", confirm_samples=1, release_window_s=1.0, cooldown_s=0.0)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.0), now=0.0)
    # brief absence: still held (grace)
    update = filt.observe(None, now=0.5)
    assert update.state is not None and update.state.value == "thumb_up"
    assert update.events == ()
    # grace elapsed: released once
    update = filt.observe(None, now=1.0)
    assert update.state is None
    assert [e.event for e in update.events] == ["gesture_thumb_up_released"]
    # absence continues: no duplicate release
    update = filt.observe(None, now=1.5)
    assert update.events == ()


def test_holding_five_seconds_emits_approximately_one_event():
    filt = EvidenceFilter(
        "gesture", confirm_samples=2, release_window_s=2.0, ttl_s=10.0
    )
    events = []
    for t in (0.0, 0.1, 1.0, 2.0, 3.0, 4.0, 5.0):
        update = filt.observe(_raw("thumb_up", 0.9, observed_at=t), now=t)
        events.extend(update.events)
    assert [e.event for e in events] == ["gesture_thumb_up_confirmed"]
    # released exactly once after the hold ends
    events = []
    for t in (5.1, 6.0, 7.2, 8.0):
        update = filt.observe(None, now=t)
        events.extend(update.events)
    assert [e.event for e in events] == ["gesture_thumb_up_released"]


def test_switch_requires_confirmation_hysteresis():
    filt = EvidenceFilter("gesture", confirm_samples=2)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.0), now=0.0)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.1), now=0.1)  # confirmed
    # a single different value does NOT switch
    update = filt.observe(_raw("victory", 0.91, observed_at=0.2), now=0.2)
    assert update.state is not None and update.state.value == "thumb_up"
    assert update.events == ()
    assert update.pending is not None and update.pending.value == "victory"
    # second different value: switch → released + confirmed
    update = filt.observe(_raw("victory", 0.93, observed_at=0.3), now=0.3)
    assert update.state is not None and update.state.value == "victory"
    assert [e.event for e in update.events] == [
        "gesture_thumb_up_released",
        "gesture_victory_confirmed",
    ]


def test_hysteresis_confidence_delta_gates_switch():
    filt = EvidenceFilter("gesture", confirm_samples=2, hysteresis_conf=0.05)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.0), now=0.0)
    filt.observe(_raw("thumb_up", 0.9, observed_at=0.1), now=0.1)  # confirmed at 0.9
    # victory at 0.90 does not clear the delta (needs >= 0.95)
    update = filt.observe(_raw("victory", 0.90, observed_at=0.2), now=0.2)
    assert update.state is not None and update.state.value == "thumb_up"
    assert update.rejected and update.rejected[0].reason == RejectionReason.SWITCH_PENDING
    assert update.pending is None  # does not advance the switch count


# ---------------------------------------------------------------------------
# TTL / staleness
# ---------------------------------------------------------------------------


def test_ttl_expiry_releases_state():
    filt = EvidenceFilter("person", confirm_samples=1, ttl_s=3.0, release_window_s=None)
    update = filt.observe(_raw("present", 0.9, observed_at=0.0, kind="person"), now=0.0)
    assert update.state is not None
    assert update.state.expires_at == pytest.approx(3.0)
    assert not update.state.is_stale(2.0)
    assert update.state.is_stale(3.5)
    update = filt.observe(None, now=3.5)
    assert update.state is None
    assert [e.event for e in update.events] == ["person_present_released"]


def test_stale_state_never_surfaces_as_current():
    filt = EvidenceFilter("person", confirm_samples=1, ttl_s=1.0, release_window_s=None)
    filt.observe(_raw("present", 0.9, observed_at=0.0, kind="person"), now=0.0)
    assert filt.state(5.0) is None  # expired: not current truth
    assert filt.observe(None, now=5.0).state is None


def test_refresh_extends_expiry():
    filt = EvidenceFilter("person", confirm_samples=1, ttl_s=1.0, release_window_s=None)
    filt.observe(_raw("present", 0.9, observed_at=0.0, kind="person"), now=0.0)
    filt.observe(_raw("present", 0.9, observed_at=0.8, kind="person"), now=0.8)
    assert filt.state(1.5) is not None  # refreshed: expires at 1.8
    assert filt.state(1.9) is None


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_cooldown_suppresses_repeat_confirm():
    filt = EvidenceFilter("gesture", confirm_samples=1, release_window_s=0.1, cooldown_s=2.0)
    update = filt.observe(_raw("thumb_up", 0.9, observed_at=0.0), now=0.0)
    assert [e.event for e in update.events] == ["gesture_thumb_up_confirmed"]
    # released after the grace, then re-confirmed inside cooldown → event suppressed
    filt.observe(None, now=0.2)
    update = filt.observe(_raw("thumb_up", 0.9, observed_at=0.3), now=0.3)
    assert update.state is not None  # state is still stable
    assert update.events == ()  # but no duplicate event


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_filter_validates_parameters():
    with pytest.raises(ValueError):
        EvidenceFilter("gesture", min_confidence=1.5)
    with pytest.raises(ValueError):
        EvidenceFilter("gesture", confirm_samples=0)
    with pytest.raises(ValueError):
        EvidenceFilter("gesture", ttl_s=-1)
    with pytest.raises(ValueError):
        EvidenceFilter("gesture", hysteresis_conf=2.0)


def test_raw_observation_validates():
    with pytest.raises(ValueError):
        RawObservation("", "gesture", "thumb_up", 0.9, 0.0)
    with pytest.raises(ValueError):
        RawObservation("gesture", "gesture", "thumb_up", 1.5, 0.0)
    with pytest.raises(ValueError):
        RawObservation("gesture", "gesture", "thumb_up", 0.9, math.inf)


def test_observe_rejects_mismatched_key():
    filt = EvidenceFilter("gesture")
    with pytest.raises(ValueError):
        filt.observe(_raw("thumb_up", 0.9, observed_at=0.0, kind="person"), now=0.0)


# ---------------------------------------------------------------------------
# EvidenceHub aggregation
# ---------------------------------------------------------------------------


def _hub_raw(value, conf, *, t, source="gesture", kind="gesture", track=None):
    return RawObservation(source, kind, value, conf, t, track)


def test_hub_routes_multiple_sources_and_kinds():
    hub = EvidenceHub(confirm_samples=1)
    snapshot = hub.observe(
        [
            _hub_raw("present", 0.9, t=0.0, source="yunet", kind="person"),
            _hub_raw("thumb_up", 0.9, t=0.0, source="gesture", kind="gesture"),
        ],
        now=0.0,
    )
    assert set(snapshot.state_values()) == {"present", "thumb_up"}
    assert set(snapshot.event_values()) == {
        "person_present_confirmed",
        "gesture_thumb_up_confirmed",
    }
    assert hub.state_for("person") is not None
    assert hub.state_for("gesture") is not None


def test_hub_absent_tick_sweeps_all_keys():
    hub = EvidenceHub(confirm_samples=1, release_window_s=0.5)
    hub.observe([_hub_raw("thumb_up", 0.9, t=0.0)], now=0.0)
    snapshot = hub.refresh(now=1.0)
    assert snapshot.state_values() == ()
    assert "gesture_thumb_up_released" in snapshot.event_values()


def test_hub_tracks_entities_independently_by_track_id():
    hub = EvidenceHub(confirm_samples=1, release_window_s=0.5)
    hub.observe(
        [
            _hub_raw("open_palm", 0.9, t=0.0, track="hand-1"),
            _hub_raw("victory", 0.9, t=0.0, track="hand-2"),
        ],
        now=0.0,
    )
    assert {hub.state_for("gesture", "hand-1").value} == {"open_palm"}
    assert hub.state_for("gesture", "hand-2").value == "victory"
    # hand-1 disappears; hand-2 remains
    hub.observe(
        [_hub_raw("victory", 0.9, t=0.1, track="hand-2")], now=0.1
    )
    assert hub.state_for("gesture", "hand-1") is not None  # grace window
    hub.refresh(now=0.55)  # hand-1 (0.0+0.5) released; hand-2 (0.1+0.5) held
    assert hub.state_for("gesture", "hand-1") is None
    assert hub.state_for("gesture", "hand-2") is not None


def test_hub_reset_drops_all_perception():
    hub = EvidenceHub(confirm_samples=1)
    hub.observe([_hub_raw("thumb_up", 0.9, t=0.0)], now=0.0)
    hub.reset()
    assert hub.state_for("gesture") is None