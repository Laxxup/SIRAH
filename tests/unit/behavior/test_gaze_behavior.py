"""GazeBehavior tests (Stage 8): emit-on-movement, silence on stability,
saccade on first target, recenter."""

from __future__ import annotations

from sirah.behavior.gaze_behavior import GazeBehavior
from sirah.perception.contracts import GazeTarget


def test_first_target_emits_immediately():
    behavior = GazeBehavior()
    sp = behavior.step(GazeTarget(0.6, -0.2, confidence=0.9))
    assert sp is not None
    assert sp.x == 0.6
    assert sp.y == -0.2


def test_unchanged_target_stays_silent():
    behavior = GazeBehavior()
    behavior.step(GazeTarget(0.6, -0.2))
    assert behavior.step(GazeTarget(0.6, -0.2)) is None


def test_moved_target_emits_new_setpoint():
    behavior = GazeBehavior()
    behavior.step(GazeTarget(0.6, -0.2))
    sp = behavior.step(GazeTarget(0.4, -0.2))
    assert sp is not None
    assert sp.x == 0.5  # EMA halfway, not the raw sample
    assert sp.y == -0.2


def test_convergence_stops_emitting():
    behavior = GazeBehavior(alpha=0.5, emit_eps=0.001)
    behavior.step(GazeTarget(0.6, -0.2))
    emitted = 0
    for _ in range(60):
        if behavior.step(GazeTarget(0.6, -0.2)) is not None:
            emitted += 1
    assert emitted <= 1  # snap + emit_eps silence the tail


def test_recenter_resets_saccade():
    behavior = GazeBehavior()
    behavior.step(GazeTarget(0.6, -0.2))
    behavior.recenter()
    sp = behavior.step(GazeTarget(-0.5, 0.3))
    assert sp is not None
    assert sp.x == -0.5  # fresh saccade: jump, not EMA from 0.6