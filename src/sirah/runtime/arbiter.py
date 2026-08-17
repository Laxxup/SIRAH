"""Eye arbitration (M8): which gaze producer owns the eyes this tick.

Before blink, idle motion, conversation gaze and expressions can fight
over the same actuators, the runtime needs one deterministic place that
decides WHO moves the eyes. Each producer either claims the eyes with a
`Setpoint` or yields (returns None). The arbiter grants the highest-
priority non-yielding claim:

    safety > manual > face_tracking > idle

- SAFETY and MANUAL override face tracking by construction (they sort
  first); the runtime wires their providers, which are None (no claim)
  until an explicit operator action installs them.
- Composition beats exclusion: gaze owns X/Y while blink (firmware-owned,
  ADR-0004) owns eyelids — arbitration never needs a global lock.
- The arbiter is stateless and deterministic; producer state (hold,
  recenter, idle wander) lives inside the producers.

This is policy, not hardware: the winning `Setpoint` still passes through
`SetpointGate` and the firmware limits before anything moves.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from sirah.runtime.policies import Setpoint

DEFAULT_PRIORITIES: tuple[str, ...] = (
    "safety",
    "manual",
    "face_tracking",
    "idle",
)


class Producer:
    """Canonical gaze producer names (arbitration identity)."""

    SAFETY = "safety"
    MANUAL = "manual"
    FACE_TRACKING = "face_tracking"
    IDLE = "idle"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class GazeClaim:
    """The granted producer and its setpoint for one tick."""

    producer: str
    setpoint: Setpoint
    acquired_at: float


class EyeArbiter:
    """Grants the eye actuators to the highest-priority claiming producer."""

    def __init__(self, priorities: tuple[str, ...] = DEFAULT_PRIORITIES) -> None:
        if not priorities:
            raise ValueError("priorities must not be empty")
        if len(set(priorities)) != len(priorities):
            raise ValueError("priorities must not contain duplicates")
        if any(not name for name in priorities):
            raise ValueError("producer names must be non-empty")
        self.priorities = priorities

    def arbitrate(
        self, claims: Mapping[str, Setpoint | None], *, now: float
    ) -> GazeClaim | None:
        """Grant a claim by priority order; None when every producer yields."""
        if not isfinite(now):
            raise ValueError("now must be finite")
        for producer in self._order(claims):
            setpoint = claims.get(producer)
            if setpoint is not None:
                return GazeClaim(producer, setpoint, now)
        return None

    def _order(self, claims: Mapping[str, Setpoint | None]) -> tuple[str, ...]:
        ordered = tuple(name for name in self.priorities if name in claims)
        extras = tuple(name for name in claims if name not in self.priorities)
        return ordered + extras