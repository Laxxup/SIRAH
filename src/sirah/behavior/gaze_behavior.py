"""Gaze behavior (Stage 8): detection → next gaze intention.

The cognitive core of the eyes subsystem: perception reports
`GazeTarget` (world state, A1 normalized), this module decides the next
`Setpoint`. Rules held here:

- Smooth the raw target (jitter rejection) with jump-on-first (saccade).
- Emit a Setpoint ONLY when the smoothed target moved beyond `emit_eps`
  since the last emission — the wire stays silent otherwise (no TARGET
  spam at 50 Hz; the gate and firmware do the rest).

Boundaries (ADR-0004): this module NEVER sends, never clamps against
physical limits (SetpointGate in runtime/policies.py), and never decides
safety — those live in the runtime policy layer and the firmware.
"""

from __future__ import annotations

from sirah.behavior.smooth import ExponentialSmoother
from sirah.perception.contracts import GazeTarget
from sirah.runtime.policies import Setpoint


class GazeBehavior:
    """Gaze decision policy: EMA-smooth targets, emit on movement."""

    def __init__(
        self,
        alpha: float = 0.5,
        snap_eps: float = 0.001,
        emit_eps: float = 0.001,
    ) -> None:
        self._smoother = ExponentialSmoother(alpha=alpha, snap_eps=snap_eps)
        self._emit_eps = emit_eps
        self._last_emitted: Setpoint | None = None

    def step(self, target: GazeTarget) -> Setpoint | None:
        """One decision from one detection."""
        x, y = self._smoother.update(target.x, target.y)
        candidate = Setpoint(x, y)
        if self._last_emitted is None:
            self._last_emitted = candidate
            return candidate
        moved = (
            abs(candidate.x - self._last_emitted.x) >= self._emit_eps
            or abs(candidate.y - self._last_emitted.y) >= self._emit_eps
        )
        if not moved:
            return None
        self._last_emitted = candidate
        return candidate

    def recenter(self) -> None:
        """Clear smoother state: next face is a fresh saccade."""
        self._smoother.reset()
        self._last_emitted = None