"""Behavior contracts (Stage 8): nominal interfaces for the decision layer.

Behavior DECIDES: it converts perception output (GazeTarget) into the
next physical intention (Setpoint). It never talks to hardware — the
runtime gates and sends (SetpointGate + firmware limits, ADR-0004).
"""

from __future__ import annotations

from collections.abc import Sequence
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


@runtime_checkable
class AttentionSelector(Protocol):
    """Stabilize one primary target from a frame's detections.

    ATTENTION decides which of several detected faces matters and holds it
    through jitter and brief loss (anti-flicker); the concrete manager
    lives in sirah.behavior.attention and satisfies this boundary.
    """

    def observe(self, faces: Sequence[GazeTarget]) -> GazeTarget | None: ...