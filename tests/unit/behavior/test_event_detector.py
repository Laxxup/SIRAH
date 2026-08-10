from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from sirah.behavior.event_detector import EventDetector


@dataclass(frozen=True)
class Snapshot:
    observed_at: float
    present: bool
    x: float | None
    y: float | None
    confidence: float | None
    source_state: Literal["tracking", "lost", "searching"]


FIXTURE = Path(__file__).parents[2] / "fixtures/behavior/future_behavior_sequences.jsonl"


def test_golden_sequence_emits_edges_after_hysteresis_and_cooldown():
    detector = EventDetector()
    observed: list[str | None] = []

    for line in FIXTURE.read_text().splitlines():
        row = json.loads(line)
        expected = row.pop("expected_event")
        event = detector.observe(Snapshot(**row))
        observed.append(None if event is None else event.kind.value)
        assert observed[-1] == expected


def test_opposite_sample_resets_hysteresis():
    detector = EventDetector(arrival_samples=2, loss_samples=2)

    assert detector.observe(Snapshot(0.0, True, 0.0, 0.0, 1.0, "tracking")) is None
    assert detector.observe(Snapshot(1.0, False, None, None, None, "lost")) is None
    assert detector.observe(Snapshot(2.0, True, 0.0, 0.0, 1.0, "tracking")) is None
    event = detector.observe(Snapshot(3.0, True, 0.0, 0.0, 1.0, "tracking"))

    assert event is not None
    assert event.kind.value == "person_arrived"


def test_arrival_and_loss_thresholds_are_configurable():
    detector = EventDetector(arrival_samples=1, loss_samples=1, cooldown_s=0.0)

    arrived = detector.observe(Snapshot(0.0, True, 0.0, 0.0, 1.0, "tracking"))
    lost = detector.observe(Snapshot(1.0, False, None, None, None, "searching"))

    assert arrived is not None and arrived.kind.value == "person_arrived"
    assert lost is not None and lost.kind.value == "person_lost"


def test_initial_absence_establishes_state_without_a_loss_event():
    detector = EventDetector()

    assert detector.observe(Snapshot(0.0, False, None, None, None, "lost")) is None
    assert detector.observe(Snapshot(1.0, False, None, None, None, "searching")) is None


def test_tracking_snapshot_requires_coordinates_and_confidence():
    detector = EventDetector()

    with pytest.raises(ValueError, match="tracking"):
        detector.observe(Snapshot(0.0, True, None, None, None, "tracking"))


def test_observed_time_must_not_move_backwards():
    detector = EventDetector()
    detector.observe(Snapshot(1.0, True, 0.0, 0.0, 1.0, "tracking"))

    with pytest.raises(ValueError, match="monotonic"):
        detector.observe(Snapshot(0.0, True, 0.0, 0.0, 1.0, "tracking"))


def test_source_state_must_be_known():
    detector = EventDetector()

    with pytest.raises(ValueError, match="source_state"):
        detector.observe(Snapshot(0.0, False, None, None, None, "unknown"))  # type: ignore[arg-type]


def test_observed_time_must_be_finite():
    detector = EventDetector()

    with pytest.raises(ValueError, match="finite"):
        detector.observe(Snapshot(float("nan"), True, 0.0, 0.0, 1.0, "tracking"))
