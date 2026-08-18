"""M6 person data model tests: validation, canonical coordinates,
provenance, ObservedScene semantics — no mediapipe, no hardware."""

from __future__ import annotations

import pytest

from sirah.perception.person import (
    ObservedScene,
    PersonDetection,
    PersonTrack,
    TrackLifecycle,
    box_intersects_frame,
)


def _det(**overrides) -> PersonDetection:
    values = {
        "x": 0.2,
        "y": 0.1,
        "width": 0.4,
        "height": 0.6,
        "confidence": 0.9,
        "source_frame_index": 7,
        "produced_at": 100.0,
        "captured_at": 99.9,
        "detector": "fake",
    }
    values.update(overrides)
    return PersonDetection(**values)


def test_detection_valid():
    d = _det()
    assert d.center == (0.4, 0.4)
    assert d.detector == "fake"
    assert d.source_frame_index == 7


@pytest.mark.parametrize(
    "field,value",
    [
        ("x", float("nan")),
        ("y", float("inf")),
        ("width", -0.1),
        ("height", 0.0),
        ("confidence", 1.5),
        ("confidence", -0.01),
        ("source_frame_index", -1),
        ("produced_at", float("nan")),
        ("captured_at", float("inf")),
        ("detector", ""),
    ],
)
def test_detection_rejects_invalid(field, value):
    with pytest.raises(ValueError):
        _det(**{field: value})


def test_detection_rejects_box_fully_off_frame():
    # box entirely left/above of the frame is NOT an observation
    with pytest.raises(ValueError):
        _det(x=-1.5, y=0.2, width=0.5, height=0.5)
    with pytest.raises(ValueError):
        _det(x=1.1, y=0.2, width=0.3, height=0.3)
    with pytest.raises(ValueError):
        _det(x=0.2, y=1.2, width=0.3, height=0.3)


def test_detection_accepts_box_spilling_frame_edge():
    # a real person entering/exiting may spill a few pixels: keep it
    d = _det(x=0.9, y=0.1, width=0.2, height=0.6)
    assert d.width == 0.2
    assert d.x == 0.9  # canonical values never clamped


def test_box_intersects_frame():
    assert box_intersects_frame(0.0, 0.0, 1.0, 1.0)
    assert box_intersects_frame(0.9, 0.1, 0.2, 0.6)
    assert not box_intersects_frame(1.1, 0.2, 0.3, 0.3)
    assert not box_intersects_frame(-1.5, 0.2, 0.5, 0.5)


def test_track_snapshot_valid():
    t = PersonTrack(
        track_id=3,
        lifecycle=TrackLifecycle.CONFIRMED,
        x=0.2,
        y=0.1,
        width=0.4,
        height=0.6,
        confidence=0.9,
        first_seen=100.0,
        last_seen=100.3,
        last_source_frame_index=7,
        velocity=(0.1, 0.0),
    )
    assert t.observed_now
    assert t.track_id == 3


def test_track_lost_is_not_observed_now():
    t = PersonTrack(
        track_id=0,
        lifecycle=TrackLifecycle.TEMPORARILY_LOST,
        x=0.2,
        y=0.1,
        width=0.4,
        height=0.6,
        confidence=0.9,
        first_seen=100.0,
        last_seen=100.3,
        last_source_frame_index=7,
    )
    assert not t.observed_now


@pytest.mark.parametrize(
    "field,value",
    [
        ("track_id", -1),
        ("x", float("nan")),
        ("width", 0.0),
        ("confidence", 1.2),
        ("first_seen", 101.0),  # after last_seen=100.3
        ("last_seen", 99.0),  # before first_seen=100.0
        ("last_source_frame_index", -2),
        ("detector", ""),
    ],
)
def test_track_rejects_invalid(field, value):
    kwargs = {
        "track_id": 1,
        "lifecycle": TrackLifecycle.CONFIRMED,
        "x": 0.2,
        "y": 0.1,
        "width": 0.4,
        "height": 0.6,
        "confidence": 0.9,
        "first_seen": 100.0,
        "last_seen": 100.3,
        "last_source_frame_index": 7,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        PersonTrack(**kwargs)


def test_track_rejects_nonfinite_velocity():
    with pytest.raises(ValueError):
        PersonTrack(
            track_id=1,
            lifecycle=TrackLifecycle.CONFIRMED,
            x=0.2,
            y=0.1,
            width=0.4,
            height=0.6,
            confidence=0.9,
            first_seen=100.0,
            last_seen=100.3,
            last_source_frame_index=7,
            velocity=(float("nan"), 0.0),
        )


def _track(lifecycle: TrackLifecycle, track_id: int = 0) -> PersonTrack:
    return PersonTrack(
        track_id=track_id,
        lifecycle=lifecycle,
        x=0.2,
        y=0.1,
        width=0.4,
        height=0.6,
        confidence=0.9,
        first_seen=100.0,
        last_seen=100.3,
        last_source_frame_index=7,
    )


def test_observed_scene_counts_only_observed_now():
    scene = ObservedScene(
        tracks=(
            _track(TrackLifecycle.CONFIRMED, 0),
            _track(TrackLifecycle.TENTATIVE, 1),
            _track(TrackLifecycle.TEMPORARILY_LOST, 2),
        ),
        observed_at=101.0,
        source_frame_index=9,
    )
    assert scene.person_count == 2
    assert scene.person_present
    assert len(scene.active) == 2
    assert [t.track_id for t in scene.temporarily_lost] == [2]


def test_observed_scene_empty():
    scene = ObservedScene(tracks=(), observed_at=101.0, source_frame_index=9)
    assert scene.person_count == 0
    assert not scene.person_present


def test_observed_scene_validation():
    with pytest.raises(ValueError):
        ObservedScene(tracks=(), observed_at=float("nan"), source_frame_index=0)
    with pytest.raises(ValueError):
        ObservedScene(tracks=(), observed_at=0.0, source_frame_index=-1)
    with pytest.raises(ValueError):
        ObservedScene(tracks=(), observed_at=0.0, source_frame_index=0, camera_fps=-1.0)