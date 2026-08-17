"""WorldState (M9): a minimal typed snapshot of what SIRAH currently perceives.

PERCEPTION observes; WORLD STATE represents. This frozen snapshot describes
the current reality for behavior, attention and (later) conversation
consumers — it never decides behavior and never holds mutable global state.

Only genuinely useful state is represented:

- vision: whether a face is present now, the attended target, and how
  fresh the last detection is (target_age_s);
- robot: the granted gaze setpoint and which producer won it (arbiter);
- availability: whether perception is degraded.

`WorldStateBuilder` accumulates perception ticks and emits immutable
`WorldState` snapshots, so consumers always read a consistent state.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from sirah.perception.contracts import GazeTarget


@dataclass(frozen=True)
class WorldState:
    """Immutable current-state snapshot (A1 normalized coordinates)."""

    face_present: bool
    primary_target: GazeTarget | None
    last_observed_at: float | None
    target_age_s: float | None
    gaze_x: float | None
    gaze_y: float | None
    gaze_producer: str | None
    vision_degraded: bool
    observed_at: float

    def __post_init__(self) -> None:
        if not isfinite(self.observed_at):
            raise ValueError("observed_at must be finite")
        if self.face_present:
            if self.primary_target is None or self.last_observed_at is None:
                raise ValueError("face_present requires a target and last_observed_at")
            if self.target_age_s is None or self.target_age_s < 0 or not isfinite(self.target_age_s):
                raise ValueError("target_age_s must be a non-negative finite age")
            if not isfinite(self.last_observed_at):
                raise ValueError("last_observed_at must be finite")
            x, y = self.primary_target.x, self.primary_target.y
            if not -1.0 <= x <= 1.0 or not -1.0 <= y <= 1.0:
                raise ValueError("primary_target coordinates must be normalized")
        else:
            if self.primary_target is not None:
                raise ValueError("no face requires primary_target None")
        if self.gaze_x is None:
            if self.gaze_y is not None or self.gaze_producer is not None:
                raise ValueError("no gaze setpoint requires gaze_y/gaze_producer None")
        else:
            if self.gaze_y is None or self.gaze_producer is None:
                raise ValueError("a gaze setpoint requires gaze_y and gaze_producer")
            if not -1.0 <= self.gaze_x <= 1.0 or not -1.0 <= self.gaze_y <= 1.0:
                raise ValueError("gaze setpoint coordinates must be normalized")


class WorldStateBuilder:
    """Accumulates perception ticks and emits frozen WorldState snapshots."""

    def __init__(self) -> None:
        self._current_target: GazeTarget | None = None
        self._current_at: float | None = None
        self._last_target: GazeTarget | None = None
        self._last_seen_at: float | None = None

    def observe(self, target: GazeTarget | None, *, now: float) -> None:
        """Record one perception tick (target is None when no face seen)."""
        if not isfinite(now):
            raise ValueError("now must be finite")
        self._current_target = target
        self._current_at = now
        if target is not None:
            self._last_target = target
            self._last_seen_at = now

    def snapshot(
        self,
        *,
        now: float,
        gaze_x: float | None,
        gaze_y: float | None,
        gaze_producer: str | None,
        vision_degraded: bool,
    ) -> WorldState:
        """Emit the current immutable state."""
        present = self._current_target is not None
        target_age = (
            now - self._last_seen_at if self._last_seen_at is not None else None
        )
        return WorldState(
            face_present=present,
            primary_target=self._current_target if present else None,
            last_observed_at=self._last_seen_at,
            target_age_s=target_age,
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            gaze_producer=gaze_producer,
            vision_degraded=vision_degraded,
            observed_at=now,
        )