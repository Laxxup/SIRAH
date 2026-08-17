"""Attention manager (M10): choose and hold the primary visual target.

Perception detects every face (`MultiFaceDetector`); ATTENTION decides
which one matters. This layer is deterministic, frame-count based and
independent of servo calibration, models, transport and conversation:

- ACQUISITION: with no primary, adopt the highest-confidence face only
  after `acquire_samples` consecutive frames (no flicker on startup).
- CONTINUITY: while a primary exists, the face nearest to it (within
  `continuity_gate`) is the same target; small detector jitter never
  changes identity.
- LOSS HOLD: when no face matches, the primary is HELD for
  `loss_hold_samples` frames so brief gaps do not recenter the eyes.
- REPLACEMENT: a persistent alternative (same face for `switch_samples`)
  replaces the primary; if nothing stabilizes, the stale target is
  released (bounded attention, never a frozen lock).

The attention layer outputs a single `GazeTarget` the behavior layer can
smooth; it never maps coordinates to servos and never talks to hardware.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import hypot

from sirah.perception.contracts import GazeTarget

DEFAULT_ACQUIRE_SAMPLES = 2
DEFAULT_SWITCH_SAMPLES = 3
DEFAULT_LOSS_HOLD_SAMPLES = 5
DEFAULT_CONTINUITY_GATE = 0.4
DEFAULT_SWITCH_EPS = 0.1


def _distance(a: GazeTarget, b: GazeTarget) -> float:
    return hypot(a.x - b.x, a.y - b.y)


class AttentionManager:
    """Primary-target selection with anti-flicker hysteresis."""

    def __init__(
        self,
        *,
        acquire_samples: int = DEFAULT_ACQUIRE_SAMPLES,
        switch_samples: int = DEFAULT_SWITCH_SAMPLES,
        loss_hold_samples: int = DEFAULT_LOSS_HOLD_SAMPLES,
        continuity_gate: float = DEFAULT_CONTINUITY_GATE,
        switch_eps: float = DEFAULT_SWITCH_EPS,
    ) -> None:
        if acquire_samples < 1 or switch_samples < 1 or loss_hold_samples < 1:
            raise ValueError("sample thresholds must be at least one")
        if continuity_gate < 0 or switch_eps < 0:
            raise ValueError("distance thresholds must not be negative")
        self.acquire_samples = acquire_samples
        self.switch_samples = switch_samples
        self.loss_hold_samples = loss_hold_samples
        self.continuity_gate = continuity_gate
        self.switch_eps = switch_eps
        self._primary: GazeTarget | None = None
        self._candidate: GazeTarget | None = None
        self._candidate_count = 0
        self._absent = 0

    def observe(self, faces: Sequence[GazeTarget]) -> GazeTarget | None:
        """One attention decision from one frame's detections."""
        if self._primary is None:
            return self._acquire(faces)
        primary = self._primary
        if faces:
            nearest = min(faces, key=lambda face: _distance(face, primary))
            if _distance(nearest, primary) <= self.continuity_gate:
                self._absent = 0
                self._candidate = None
                self._candidate_count = 0
                return nearest
        return self._handle_loss(faces)

    def reset(self) -> None:
        """Drop attention state: the next frame starts a fresh acquisition."""
        self._primary = None
        self._candidate = None
        self._candidate_count = 0
        self._absent = 0

    def primary(self) -> GazeTarget | None:
        """Current held primary (read-only; for diagnostics)."""
        return self._primary

    def _acquire(self, faces: Sequence[GazeTarget]) -> GazeTarget | None:
        if not faces:
            return None
        best = max(faces, key=lambda face: face.confidence)
        if self._candidate is None or _distance(best, self._candidate) > self.switch_eps:
            self._candidate = best
            self._candidate_count = 1
        else:
            self._candidate_count += 1
        if self._candidate_count >= self.acquire_samples:
            self._primary = self._candidate
            self._candidate = None
            self._candidate_count = 0
            return self._primary
        return None

    def _handle_loss(self, faces: Sequence[GazeTarget]) -> GazeTarget | None:
        self._absent += 1
        if self._absent < self.loss_hold_samples:
            return self._primary  # brief loss: hold the recent target
        if self._absent >= self.loss_hold_samples + self.switch_samples:
            self._release()
            return None
        if not faces:
            self._release()
            return None
        best = max(faces, key=lambda face: face.confidence)
        if self._candidate is None or _distance(best, self._candidate) > self.switch_eps:
            self._candidate = best
            self._candidate_count = 1
        else:
            self._candidate_count += 1
        if self._candidate_count >= self.switch_samples:
            self._primary = self._candidate
            self._candidate = None
            self._candidate_count = 0
            self._absent = 0
            return self._primary
        return self._primary  # still holding while a replacement stabilizes

    def _release(self) -> None:
        self._primary = None
        self._candidate = None
        self._candidate_count = 0
        self._absent = 0