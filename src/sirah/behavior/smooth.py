"""Exponential moving-average smoother for gaze targets (Stage 8).

Stability over precision (investigation-stage8): raw detections jitter;
the pipeline converges on the smoothed center while firmware handles the
physical easing (ADR-0005). Semantics:

- First sample jumps to the target (a saccade: the eyes snap to a new
  face instead of crawling from the previous spot).
- Subsequent samples converge exponentially; near the target the value
  snaps to it (no sub-epsilon drift, matches the firmware SNAP_EPS
  philosophy).
- `reset()` clears state — e.g. when a face disappears and reappears,
  the new target should be treated as a fresh saccade.

No I/O, no clock, pure math: fully unit-testable.
"""

from __future__ import annotations

DEFAULT_ALPHA = 0.5
DEFAULT_SNAP_EPS = 0.001


class ExponentialSmoother:
    """One axis-independent 2D EMA stage with jump-on-first-sample."""

    def __init__(self, alpha: float = DEFAULT_ALPHA, snap_eps: float = DEFAULT_SNAP_EPS) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"smoother alpha must be in (0, 1], got {alpha}")
        self.alpha = alpha
        self.snap_eps = snap_eps
        self.x = 0.0
        self.y = 0.0
        self._initialized = False

    def update(self, x: float, y: float) -> tuple[float, float]:
        """Feed one sample; returns the smoothed (x, y)."""
        if not self._initialized:
            self._initialized = True
            self.x, self.y = x, y
        else:
            self.x += (x - self.x) * self.alpha
            self.y += (y - self.y) * self.alpha
        if abs(x - self.x) < self.snap_eps:
            self.x = x
        if abs(y - self.y) < self.snap_eps:
            self.y = y
        return self.x, self.y

    def reset(self) -> None:
        """Drop state: the next update jumps to the new target."""
        self._initialized = False
        self.x = 0.0
        self.y = 0.0