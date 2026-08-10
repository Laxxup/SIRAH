"""Edge-triggered semantic events from perception snapshots."""

from __future__ import annotations

import math
from typing import Literal, Protocol

from sirah.behavior.future_contracts import BehaviorEvent, EventKind


class PerceptionObservation(Protocol):
    """Structural boundary fulfilled by the future PerceptionSnapshot."""

    observed_at: float
    present: bool
    x: float | None
    y: float | None
    confidence: float | None
    source_state: Literal["tracking", "lost", "searching"]


class EventDetector:
    """Detect arrival/loss edges with deterministic hysteresis and cooldowns."""

    def __init__(
        self,
        *,
        arrival_samples: int = 2,
        loss_samples: int = 2,
        cooldown_s: float = 5.0,
    ) -> None:
        if arrival_samples < 1 or loss_samples < 1:
            raise ValueError("sample thresholds must be at least one")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must not be negative")
        self._arrival_samples = arrival_samples
        self._loss_samples = loss_samples
        self._cooldown_s = cooldown_s
        self._tracking_count = 0
        self._absent_count = 0
        self._semantic_present: bool | None = None
        self._last_observed_at: float | None = None
        self._last_emitted: dict[EventKind, float] = {}

    def observe(self, snapshot: PerceptionObservation) -> BehaviorEvent | None:
        """Consume one semantic snapshot using only its monotonic timestamp."""
        self._validate(snapshot)
        if (
            self._last_observed_at is not None
            and snapshot.observed_at < self._last_observed_at
        ):
            raise ValueError("observed_at must be monotonic")
        self._last_observed_at = snapshot.observed_at

        if snapshot.source_state == "tracking":
            self._tracking_count += 1
            self._absent_count = 0
            if self._tracking_count < self._arrival_samples:
                return None
            return self._transition(True, snapshot.observed_at)

        self._absent_count += 1
        self._tracking_count = 0
        if self._absent_count < self._loss_samples:
            return None
        return self._transition(False, snapshot.observed_at)

    def _transition(self, present: bool, observed_at: float) -> BehaviorEvent | None:
        if self._semantic_present is None:
            self._semantic_present = present
            if not present:
                return None
        else:
            if self._semantic_present is present:
                return None
            self._semantic_present = present
        kind = EventKind.PERSON_ARRIVED if present else EventKind.PERSON_LOST
        previous = self._last_emitted.get(kind)
        if previous is not None and observed_at - previous < self._cooldown_s:
            return None
        self._last_emitted[kind] = observed_at
        return BehaviorEvent(kind, observed_at)

    @staticmethod
    def _validate(snapshot: PerceptionObservation) -> None:
        if not math.isfinite(snapshot.observed_at):
            raise ValueError("observed_at must be finite")
        if snapshot.source_state not in {"tracking", "lost", "searching"}:
            raise ValueError("source_state must be tracking, lost, or searching")
        values = (snapshot.x, snapshot.y, snapshot.confidence)
        if snapshot.source_state == "tracking":
            if not snapshot.present or any(value is None for value in values):
                raise ValueError("tracking snapshots require present coordinates")
            return
        if snapshot.present or any(value is not None for value in values):
            raise ValueError("lost/searching snapshots require absent coordinates")
