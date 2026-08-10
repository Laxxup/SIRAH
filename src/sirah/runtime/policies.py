"""Runtime policies (Stage 7): setpoint mirror, lost-face, lab proposal gate.

These are the PC-side safety/filtering policies between perception,
behavior and the transport:

1. `SetpointGate` — rejects setpoints outside the normalized [-1, 1] per
   axis BEFORE they reach the wire. Firmware is the final clamp authority
   (ADR-0001/0003), but the runtime never forwards a value it knows is
   outside the contract (defense in depth, REDUCES ERR 3 round-trips).
2. `LostFacePolicy` — when no face has been seen for `lost_face_center_s`,
   the gaze target returns to CENTER (0, 0) instead of holding the last
   position (legacy eyes.md behavior).
3. `LabProposalGate` — a tiny gate for laboratory proposals (ADR-0007):
   lab components provide proposals, the gate forwards them to behavior
   ONLY when lab mode is enabled and the gate is open. Off by default.
   This is the hard boundary that keeps lab experiments from controlling
   servos without an explicit decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

MIN_COORD = -1.0
MAX_COORD = 1.0


@dataclass(frozen=True)
class Setpoint:
    x: float
    y: float


class SetpointGate:
    """Rejects out-of-contract setpoints (mirror of firmware clamp range)."""

    def __init__(self) -> None:
        self.rejected = 0

    def validate(self, x: float, y: float) -> Setpoint | None:
        """Return the setpoint when within [-1, 1] both axes, else None."""
        if MIN_COORD <= x <= MAX_COORD and MIN_COORD <= y <= MAX_COORD:
            return Setpoint(x, y)
        self.rejected += 1
        return None


class LostFacePolicy:
    """Recenters the gaze after a timeout with no face (singleton clock)."""

    def __init__(self, timeout_s: float = 2.0, clock=None) -> None:
        self.timeout_s = timeout_s
        self._clock = clock or monotonic
        self._last_face_at: float | None = None

    def on_face(self) -> None:
        """Call when a face was just seen; starts/resets the timeout."""
        self._last_face_at = self._clock()

    def target(self) -> Setpoint | None:
        """CENTER when stale, otherwise None (no change) or the last target."""
        if self._last_face_at is None:
            return None
        if self._clock() - self._last_face_at >= self.timeout_s:
            self._last_face_at = None
            return Setpoint(0.0, 0.0)
        return None

    def stale(self) -> bool:
        return self._last_face_at is None


class LabProposalGate:
    """Lab proposals reach behavior only when lab mode + gate on (ADR-0007).

    `enabled` comes from the runtime env (SIRAH_LAB). The gate defaults to
    CLOSED even in lab mode: a proposal is forwarded only after an explicit
    `open()` decision call, which production code never makes.
    """

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def allows(self) -> bool:
        return self.enabled and self._open

    def apply(self, proposal: Setpoint | None) -> Setpoint | None:
        if proposal is None or not self.allows():
            return None
        return proposal