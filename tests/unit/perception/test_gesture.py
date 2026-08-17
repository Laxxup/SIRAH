"""M5 gesture tests: pure classification/allowlist core plus a fake-backed
MediaPipe adapter (no mediapipe import, no model, no hardware)."""

from __future__ import annotations

import numpy as np
import pytest

from sirah.perception.contracts import Frame
from sirah.perception.evidence import EvidenceHub
from sirah.perception.gesture import (
    GestureCategory,
    HandGesture,
    best_category,
    canonical_value,
    classify_hands,
    gesture_observations,
    is_allowed,
)
from sirah.perception.mediapipe_gesture import MediaPipeGestureRecognizer


def test_canonical_values_and_allowlist():
    assert canonical_value("Thumb_Up") == "thumb_up"
    assert canonical_value("Open_Palm") == "open_palm"
    assert canonical_value("Victory") == "victory"
    assert canonical_value("Thumb_Down") == "thumb_down"
    assert canonical_value("Closed_Fist") is None
    assert is_allowed("Open_Palm")
    assert not is_allowed("Closed_Fist")


def test_best_category_picks_highest_score():
    categories = [GestureCategory("Thumb_Up", 0.4), GestureCategory("Open_Palm", 0.9)]
    assert best_category(categories).name == "Open_Palm"
    assert best_category([]) is None


def test_classify_hands_filters_non_allowlisted():
    hands = [
        [GestureCategory("Closed_Fist", 0.95)],  # not allowlisted → dropped
        [GestureCategory("Thumb_Up", 0.88)],
    ]
    observed = classify_hands(hands, handedness=("Left", "Right"))
    assert len(observed) == 1
    assert observed[0].gesture == "thumb_up"
    assert observed[0].handedness == "Right"
    assert observed[0].confidence == pytest.approx(0.88)
    assert observed[0].index == 1


def test_classify_hands_unknown_handedness_defaults():
    observed = classify_hands([[GestureCategory("Victory", 0.8)]])
    assert observed[0].handedness == "Unknown"


def test_classify_hands_ignores_empty_hand():
    assert classify_hands([[]]) == []


def test_gesture_observations_map_to_evidence_raws():
    hands = [
        HandGesture("thumb_up", 0.9, "Right", 0),
        HandGesture("thumb_up", 0.7, "Unknown", 1),
    ]
    raws = gesture_observations(hands, observed_at=1.0)
    assert len(raws) == 2
    assert raws[0].kind == "gesture"
    assert raws[0].value == "thumb_up"
    assert raws[0].track_id == "Right"
    assert raws[1].track_id == "hand_1"


def test_evidence_confirms_gesture_then_releases():
    hub = EvidenceHub(confirm_samples=2, release_window_s=0.1, cooldown_s=1.0)
    # two consecutive thumb_up ticks → confirmed exactly once
    first = hub.observe(gesture_observations([HandGesture("thumb_up", 0.9, "Right", 0)], observed_at=0.0), now=0.0)
    assert first.states == ()
    second = hub.observe(gesture_observations([HandGesture("thumb_up", 0.9, "Right", 0)], observed_at=0.05), now=0.05)
    events = [event.event for event in second.events]
    assert "gesture_thumb_up_confirmed" in events
    state = hub.state_for("gesture", "Right")
    assert state is not None and state.value == "thumb_up"
    # absence longer than the release window → released once
    after = hub.refresh(now=0.2)
    assert "gesture_thumb_up_released" in [event.event for event in after.events]


def test_evidence_suppresses_duplicate_confirmed_events_within_cooldown():
    hub = EvidenceHub(confirm_samples=2, release_window_s=0.5, cooldown_s=1.0)
    # acquire → confirm at t=0.05 (cooldown base), release at t=0.6
    hub.observe(gesture_observations([HandGesture("thumb_up", 0.9, "Left", 0)], observed_at=0.0), now=0.0)
    second = hub.observe(gesture_observations([HandGesture("thumb_up", 0.9, "Left", 0)], observed_at=0.05), now=0.05)
    assert "gesture_thumb_up_confirmed" in [event.event for event in second.events]
    released = hub.refresh(now=0.6)
    assert "gesture_thumb_up_released" in [event.event for event in released.events]
    # re-confirm at t=0.75, only 0.7s after the last confirm → suppressed
    hub.observe(gesture_observations([HandGesture("thumb_up", 0.9, "Left", 0)], observed_at=0.7), now=0.7)
    re_acquired = hub.observe(
        gesture_observations([HandGesture("thumb_up", 0.9, "Left", 0)], observed_at=0.75), now=0.75
    )
    assert "gesture_thumb_up_confirmed" not in [event.event for event in re_acquired.events]


class FakeRecognizer:
    def __init__(self, results: list[object]) -> None:
        self._results = iter(results)
        self.timestamps: list[int] = []

    def recognize_for_video(self, image: object, timestamp_ms: int) -> object:
        self.timestamps.append(timestamp_ms)
        return next(self._results)


class FakeResult:
    def __init__(self, gestures: list[list[object]], handedness: list[list[object]]) -> None:
        self.gestures = gestures
        self.handedness = handedness


class FakeCategory:
    def __init__(self, name: str, score: float) -> None:
        self.category_name = name
        self.score = score


@pytest.fixture()
def model_file(tmp_path):
    path = tmp_path / "gesture_recognizer.task"
    path.write_bytes(b"fake")
    return path


def test_adapter_requires_existing_model(tmp_path):
    with pytest.raises(FileNotFoundError):
        MediaPipeGestureRecognizer(tmp_path / "missing.task")


def test_adapter_maps_video_result_to_hand_gestures(model_file):
    recognizer = MediaPipeGestureRecognizer(
        model_file,
        recognizer_factory=lambda _path: FakeRecognizer(
            [
                FakeResult(
                    gestures=[[FakeCategory("Thumb_Up", 0.93), FakeCategory("Open_Palm", 0.1)]],
                    handedness=[[FakeCategory("Right", 0.99)]],
                ),
                FakeResult(
                    gestures=[[FakeCategory("Closed_Fist", 0.95)]],
                    handedness=[[FakeCategory("Right", 0.99)]],
                ),
            ]
        ),
    )
    first = recognizer.recognize(Frame(index=0, payload=np.zeros((10, 10, 3), dtype=np.uint8)))
    assert len(first) == 1
    assert first[0].gesture == "thumb_up"
    assert first[0].confidence == pytest.approx(0.93)
    assert first[0].handedness == "Right"
    # non-allowlisted gesture yields no observation
    second = recognizer.recognize(Frame(index=1, payload=np.zeros((10, 10, 3), dtype=np.uint8)))
    assert second == []
    # no payload → no observation, no call
    assert recognizer.recognize(Frame(index=2, payload=None)) == []


def test_adapter_emits_monotonic_timestamps(model_file):
    recognizer = MediaPipeGestureRecognizer(
        model_file,
        recognizer_factory=lambda _path: FakeRecognizer(
            [FakeResult([], []), FakeResult([], []), FakeResult([], [])]
        ),
    )
    for index in range(3):
        recognizer.recognize(Frame(index=index, payload=np.zeros((10, 10, 3), dtype=np.uint8)))
    timestamps = recognizer._recognizer.timestamps  # type: ignore[attr-defined]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 3


def test_adapter_validates_num_hands(model_file):
    with pytest.raises(ValueError):
        MediaPipeGestureRecognizer(model_file, num_hands=0)


def test_gesture_observations_reject_below_min_confidence():
    hub = EvidenceHub(min_confidence=0.6, confirm_samples=1)
    snapshot = hub.observe(
        gesture_observations([HandGesture("thumb_up", 0.3, "Right", 0)], observed_at=0.0),
        now=0.0,
    )
    assert snapshot.states == ()
    assert snapshot.rejected
    assert snapshot.rejected[0].reason.value == "below_confidence"