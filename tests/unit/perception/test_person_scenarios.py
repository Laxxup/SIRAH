"""M6 person-centric scenario tests: deterministic temporal sequences that
model real camera observations — walk, leave/re-enter, crossing, brief
occlusion and detector drops — asserting CONSERVATIVE scene semantics.

These are the replay-style scenarios (synthetic detections, no footage):
the tracker must never claim "still at X" for a lost person, must not
fabricate identity across re-entry, and must degrade to "unknown owner"
rather than invent one.
"""

from __future__ import annotations

from sirah.perception.person import PersonDetection, TrackLifecycle
from sirah.perception.person_tracker import GreedyIoUTracker


def det(
    x: float, y: float, w: float, h: float, conf: float, fidx: int, t: float
) -> PersonDetection:
    return PersonDetection(
        x=x, y=y, width=w, height=h, confidence=conf,
        source_frame_index=fidx, produced_at=t,
    )


def _states(scene) -> dict[int, TrackLifecycle]:
    return {t.track_id: t.lifecycle for t in scene}


def test_walk_left_to_right_stays_one_track():
    tr = GreedyIoUTracker()
    t0 = 100.0
    for step in range(20):
        x = 0.1 + step * 0.04  # left -> right across the frame
        tracks = tr.update(
            [det(x, 0.2, 0.3, 0.6, 0.9, step, t0 + step * 0.1)],
            source_frame_index=step,
            now=t0 + step * 0.1,
        )
        assert len(tracks) == 1
        assert tracks[0].track_id == 0
        assert tracks[0].lifecycle in (TrackLifecycle.TENTATIVE, TrackLifecycle.CONFIRMED)
        assert 0.1 <= tracks[0].x <= 0.9
    assert tr.spawns == 1


def test_leave_and_reenter_gets_new_track_id_not_identity():
    """Exit + re-entry: a NEW track_id is honest; reusing the old id would
    claim identity the tracker cannot prove."""
    tr = GreedyIoUTracker(track_buffer_frames=10)
    t0 = 100.0
    for fidx in range(5):  # A present
        tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1)],
                  source_frame_index=fidx, now=t0 + fidx * 0.1)
    for fidx in range(5, 15):  # A gone (longer than the buffer)
        tr.update([], source_frame_index=fidx, now=t0 + fidx * 0.1)
    after_gap = tr.update([], source_frame_index=15, now=t0 + 1.5)
    assert after_gap == ()  # nothing known -> UNKNOWN, not "A still there"
    # A re-enters at a similar position: fresh track, NEVER the old id
    reentered = tr.update(
        [det(0.2, 0.2, 0.3, 0.6, 0.9, 16, t0 + 1.6)],
        source_frame_index=16, now=t0 + 1.6,
    )
    assert reentered[0].track_id == 1  # new id, not 0
    assert tr.expirations >= 1


def test_brief_occlusion_is_temporarily_lost_then_recovered():
    tr = GreedyIoUTracker(track_buffer_frames=20)
    t0 = 100.0
    for fidx in range(6):  # A visible
        tr.update([det(0.2, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1)],
                  source_frame_index=fidx, now=t0 + fidx * 0.1)
    for fidx in range(6, 9):  # B briefly occludes A
        lost = tr.update([], source_frame_index=fidx, now=t0 + fidx * 0.1)
        assert len(lost) == 1
        assert lost[0].lifecycle is TrackLifecycle.TEMPORARILY_LOST
        # conservative semantics: the track reports its LAST bbox, not a
        # claim that the person is still at that position right now
    recovered = tr.update(
        [det(0.21, 0.2, 0.3, 0.6, 0.9, 9, t0 + 0.9)],
        source_frame_index=9, now=t0 + 0.9,
    )
    assert recovered[0].track_id == 0
    assert recovered[0].lifecycle is TrackLifecycle.CONFIRMED


def test_crossing_tracks_may_swap_ids_but_never_invent_identity():
    """Two people crossing can swap track ids (a tracker reality); the
    scene must NOT present a swapped id as identity — it is a session-local
    trajectory label only."""
    tr = GreedyIoUTracker()
    t0 = 100.0
    a, b = 0.2, 0.7
    for fidx in range(8):
        tr.update(
            [det(a, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1),
             det(b, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1)],
            source_frame_index=fidx, now=t0 + fidx * 0.1,
        )
        # swap positions at the middle to force a crossing
        a, b = b, a
    # both tracks exist after the crossing sequence; ids are session-local
    # labels, not identity
    tracks = tr.update([], source_frame_index=8, now=t0 + 0.8)
    assert len(tracks) == 2
    assert len({t.track_id for t in tracks}) == 2
    # with no current observation, BOTH are recently-observed (never "current")
    assert all(t.lifecycle is TrackLifecycle.TEMPORARILY_LOST for t in tracks)


def test_detector_drops_a_person_for_observations():
    """Detector misses B for several observations: B stays recently-observed
    (never "current"), A stays current, and the counts stay truthful."""
    tr = GreedyIoUTracker(track_buffer_frames=10)
    t0 = 100.0
    # both present for a while
    for fidx in range(4):
        tr.update(
            [det(0.2, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1),
             det(0.7, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1)],
            source_frame_index=fidx, now=t0 + fidx * 0.1,
        )
    # detector only sees A now
    for fidx in range(4, 8):
        tracks = tr.update(
            [det(0.2, 0.2, 0.3, 0.6, 0.9, fidx, t0 + fidx * 0.1)],
            source_frame_index=fidx, now=t0 + fidx * 0.1,
        )
        states = _states(tracks)
        assert states.get(0) is TrackLifecycle.CONFIRMED
        assert states.get(1) is TrackLifecycle.TEMPORARILY_LOST
        observed = [t for t in tracks if t.observed_now]
        assert len(observed) == 1  # person_count is 1, not 2


def test_empty_scene_is_unknown_not_absent_identity():
    tr = GreedyIoUTracker()
    t0 = 100.0
    tracks = tr.update([], source_frame_index=0, now=t0)
    assert tracks == ()  # UNKNOWN: no person present, no invented owner