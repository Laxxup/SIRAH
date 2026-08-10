"""Behavior contracts (Stage 8): nominal interfaces for the decision layer.

Behavior DECIDES: it converts perception output (GazeTarget) into the
next physical intention (Setpoint). It never talks to hardware — the
runtime gates and sends (SetpointGate + firmware limits, ADR-0004).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sirah.perception.contracts import GazeTarget
from sirah.runtime.policies import Setpoint


@runtime_checkable
class Behavior(Protocol):
    """Next gaze intention from one detection.

    Returns None when nothing should be sent this tick (no change — the
    wire stays silent instead of spamming TARGETs). `Setpoint` lives in
    sirah.runtime.policies (the same type the gate validates).
    """

    def step(self, target: GazeTarget) -> Setpoint | None: ...