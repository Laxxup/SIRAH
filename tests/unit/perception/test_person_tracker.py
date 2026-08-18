"""GreedyIoUTracker tests (M6): ByteTrack-style association, lifecycle,
two-stage low-confidence recovery, frame-buffer expiry, determinism,
velocity and out-of-order guards — pure, deterministic, no hardware."""

from __future__ import annotations

import pytest

from sirah.perception.person import PersonDetection, TrackLifecycle
from sirah.perception.person_tracker import GreedyIoUTracker


def det(
    x: float,
    y: float,
    w: float,
    h: float,
    conf: float,
    fidx: int,
    t: float,
    produced: float | None = None,
) -> PersonDetection:
    return PersonDetection(
        x=x,
        y=y,
        width=w,
        height=h,
        confidence=conf,
        source_frame_index=fidx,
        produced_at=produced if produced is not None else t,
    )


def _lifecycle(tracks) -> list[str]:
    return [t.lifecycle.value for t in tracks]


def test_config_validation():
    with pytest.raises(ValueError):
        GreedyIoUTracker(track_thresh=0.2, low_thresh=0.5)
    with pytest.raises(ValueError):
        GreedyIoUTracker(match_thresh=1.5)
    with pytest.raises(ValueError):
        GreedyIoUTracker(track_buffer_frames=0)
    with pytest.raises(ValueError):
        GreedyIoUTracker(confirm_frames=0)


def test_tentative_to_confirmed_and_velocity():
    tr = GreedyIoUTracker(confirm_frames=2)
    t0 = 100.0
    tracks = tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    assert _lifecycle(tracks) == ["tentative"]
    tracks = tr.update(
        [det(0.22, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1)], source_frame_index=1, now=t0 + 0.1
    )
    assert _lifecycle(tracks) == ["confirmed"]
    track = tracks[0]
    assert track.track_id == 0
    assert track.first_seen == t0
    assert track.last_seen == t0 + 0.1
    assert track.velocity is not None
    # box moved right 0.02 in 0.1s -> vx ~ 0.2 /s
    assert 0.1 < track.velocity[0] < 0.3
    assert tr.spawns == 1
    assert tr.expirations == 0


def test_miss_becomes_temporarily_lost_then_expires():
    tr = GreedyIoUTracker(track_buffer_frames=5)
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1)], source_frame_index=1, now=t0 + 0.1)
    lost = tr.update([], source_frame_index=2, now=t0 + 0.2)
    assert _lifecycle(lost) == ["temporarily_lost"]
    # still alive within buffer
    alive = tr.update([], source_frame_index=4, now=t0 + 0.4)
    assert _lifecycle(alive) == ["temporarily_lost"]
    # frame-delta expiry: 5 frames since last sight -> expired
    gone = tr.update([], source_frame_index=7, now=t0 + 0.7)
    assert gone == ()
    assert tr.expirations == 1


def test_lost_recovery_requires_match():
    tr = GreedyIoUTracker()
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1)], source_frame_index=1, now=t0 + 0.1)
    tr.update([], source_frame_index=2, now=t0 + 0.2)
    # a far-away detection must NOT steal the lost track id
    tracks = tr.update(
        [det(0.8, 0.3, 0.2, 0.5, 0.9, 3, t0 + 0.3)], source_frame_index=3, now=t0 + 0.3
    )
    assert sorted(t.track_id for t in tracks) == [0, 1]
    assert {t.lifecycle for t in tracks} == {
        TrackLifecycle.TEMPORARILY_LOST,
        TrackLifecycle.TENTATIVE,
    }
    # a matching box recovers it; the one-off tentative from frame 3 was
    # never confirmed and is dropped as noise (single-hit = not a person)
    tracks = tr.update(
        [det(0.21, 0.2, 0.3, 0.6, 0.9, 4, t0 + 0.4)], source_frame_index=4, now=t0 + 0.4
    )
    assert _lifecycle(tracks) == ["confirmed"]
    assert tracks[0].track_id == 0


def test_low_confidence_recovery_second_stage():
    tr = GreedyIoUTracker(low_thresh=0.25, track_thresh=0.5, match_thresh=0.4)
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1)], source_frame_index=1, now=t0 + 0.1)
    tr.update([], source_frame_index=2, now=t0 + 0.2)
    # occluded person detected with low confidence: BYTE recovery, not a new track
    tracks = tr.update(
        [det(0.2, 0.2, 0.3, 0.6, 0.4, 3, t0 + 0.3)], source_frame_index=3, now=t0 + 0.3
    )
    assert [t.track_id for t in tracks] == [0]
    assert _lifecycle(tracks) == ["confirmed"]
    assert tr.spawns == 1


def test_two_people_stay_distinct_and_crossing_swaps_are_possible():
    tr = GreedyIoUTracker()
    t0 = 100.0
    # A left, B right
    tr.update(
        [
            det(0.1, 0.2, 0.3, 0.6, 0.9, 0, t0),
            det(0.7, 0.2, 0.3, 0.6, 0.9, 0, t0),
        ],
        source_frame_index=0,
        now=t0,
    )
    tr.update(
        [
            det(0.12, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1),
            det(0.68, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1),
        ],
        source_frame_index=1,
        now=t0 + 0.1,
    )
    tracks = tr.update(
        [
            det(0.68, 0.2, 0.3, 0.6, 0.9, 2, t0 + 0.2),
            det(0.12, 0.2, 0.3, 0.6, 0.9, 2, t0 + 0.2),
        ],
        source_frame_index=2,
        now=t0 + 0.2,
    )
    assert [t.track_id for t in tracks] == [0, 1]
    assert all(t.lifecycle is TrackLifecycle.CONFIRMED for t in tracks)
    assert tr.spawns == 2


def test_empty_detections_advance_nothing():
    tr = GreedyIoUTracker()
    t0 = 100.0
    assert tr.update([], source_frame_index=0, now=t0) == ()
    assert tr.update([], source_frame_index=1, now=t0 + 0.1) == ()


def test_out_of_order_update_ignored():
    tr = GreedyIoUTracker()
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 5, t0)], source_frame_index=5, now=t0)
    tr.update([det(0.3, 0.2, 0.3, 0.6, 0.9, 6, t0 + 0.1)], source_frame_index=6, now=t0 + 0.1)
    # repeated / older index must not corrupt newer state
    tracks = tr.update([], source_frame_index=5, now=t0 + 0.2)
    assert _lifecycle(tracks) == ["confirmed"]
    assert tr.stale_updates == 1
    with pytest.raises(ValueError):
        tr.update([], source_frame_index=-1, now=t0)


def test_tentative_unmatched_is_dropped_not_kept_lost():
    tr = GreedyIoUTracker(confirm_frames=3)
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    tracks = tr.update([], source_frame_index=1, now=t0 + 0.1)
    # a single tentative hit is noise: dropped immediately, not "lost"
    assert tracks == ()
    assert tr.expirations == 0  # dropped, not expired-through-buffer


def test_deterministic_output_ordering():
    tr = GreedyIoUTracker()
    t0 = 100.0
    tr.update(
        [
            det(0.7, 0.2, 0.3, 0.6, 0.9, 0, t0),
            det(0.1, 0.2, 0.3, 0.6, 0.9, 0, t0),
        ],
        source_frame_index=0,
        now=t0,
    )
    # input order differs from output order, but output is stable
    one = tr.update([], source_frame_index=1, now=t0 + 0.1)
    assert [t.track_id for t in one] == sorted(t.track_id for t in one)


def test_frame_delta_based_buffer_not_wall_clock():
    tr = GreedyIoUTracker(track_buffer_frames=3)
    t0 = 100.0
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 0, t0)], source_frame_index=0, now=t0)
    tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, 1, t0 + 0.1)], source_frame_index=1, now=t0 + 0.1)
    # wall time passes but only ONE frame gap: still alive
    tracks = tr.update([], source_frame_index=2, now=t0 + 10.0)
    assert _lifecycle(tracks) == ["temporarily_lost"]