"""AttentionManager tests (M10): deterministic primary-target selection.

Covers acquisition hysteresis, identity continuity under jitter, loss
hold, permanent-loss release, replacement switching and flicker
prevention with multiple faces — all without any detector or hardware.
"""

from __future__ import annotations

import pytest

from sirah.behavior.attention import AttentionManager
from sirah.perception.contracts import GazeTarget


def test_no_faces_never_acquires():
    attention = AttentionManager(acquire_samples=1)
    assert attention.observe([]) is None
    assert attention.observe([]) is None


def test_acquisition_requires_consecutive_frames():
    attention = AttentionManager(acquire_samples=2)
    face = GazeTarget(0.3, -0.2, 0.9)
    assert attention.observe([face]) is None  # not yet stable
    assert attention.observe([face]) == face


def test_jitter_keeps_same_identity():
    attention = AttentionManager(acquire_samples=1)
    first = attention.observe([GazeTarget(0.3, -0.2, 0.9)])
    assert first == GazeTarget(0.3, -0.2, 0.9)
    jittered = attention.observe([GazeTarget(0.34, -0.18, 0.6)])
    assert jittered == GazeTarget(0.34, -0.18, 0.6)  # still the same target


def test_brief_loss_holds_recent_target():
    attention = AttentionManager(acquire_samples=1, loss_hold_samples=3)
    primary = attention.observe([GazeTarget(0.3, -0.2, 0.9)])
    assert primary is not None
    assert attention.observe([]) == primary  # hold through a brief gap
    assert attention.observe([]) == primary
    assert attention.observe([]) is None  # hold expired


def test_permanent_loss_releases_and_can_reacquire():
    attention = AttentionManager(acquire_samples=1, loss_hold_samples=2)
    attention.observe([GazeTarget(0.3, -0.2, 0.9)])
    assert attention.observe([]) is not None  # hold
    assert attention.observe([]) is None  # released
    assert attention.observe([GazeTarget(0.5, 0.5, 0.8)]) == GazeTarget(0.5, 0.5, 0.8)


def test_replacement_switches_after_persistent_frames():
    attention = AttentionManager(acquire_samples=1, loss_hold_samples=2, switch_samples=2)
    a = GazeTarget(0.3, -0.2, 0.9)
    b = GazeTarget(-0.5, 0.3, 0.8)
    assert attention.observe([a]) == a
    assert attention.observe([b]) == a  # loss hold
    assert attention.observe([b]) == a  # replacement still stabilizing
    assert attention.observe([b]) == b  # switched


def test_flicker_prevention_higher_confidence_other_face():
    attention = AttentionManager(acquire_samples=1)
    a = GazeTarget(0.3, -0.2, 0.7)
    b = GazeTarget(-0.5, 0.3, 0.95)
    assert attention.observe([a, b]) == b  # acquisition picks highest confidence
    # Even when a becomes far more confident, proximity to primary keeps b.
    assert attention.observe([GazeTarget(0.3, -0.2, 0.99), b]) == b


def test_face_order_does_not_change_identity():
    attention = AttentionManager(acquire_samples=1)
    a = GazeTarget(0.3, -0.2, 0.9)
    b = GazeTarget(-0.5, 0.3, 0.8)
    attention.observe([a, b])
    assert attention.observe([b, a]) == a  # reversed order: primary unchanged


def test_unstable_replacement_is_bounded_and_released():
    attention = AttentionManager(acquire_samples=1, loss_hold_samples=2, switch_samples=2)
    attention.observe([GazeTarget(0.3, -0.2, 0.9)])
    # Faces far apart (> switch_eps): no candidate ever stabilizes.
    shifting = [
        GazeTarget(-0.5, 0.30, 0.7),
        GazeTarget(0.50, 0.40, 0.8),
        GazeTarget(-0.6, 0.50, 0.6),
    ]
    assert attention.observe([shifting[0]]) is not None  # hold
    assert attention.observe([shifting[0]]) is not None  # candidate, still holding
    assert attention.observe([shifting[1]]) is not None  # candidate changed
    assert attention.observe([shifting[2]]) is None  # never stabilized: released


def test_reset_clears_state():
    attention = AttentionManager(acquire_samples=1)
    attention.observe([GazeTarget(0.3, -0.2, 0.9)])
    assert attention.primary() is not None
    attention.reset()
    assert attention.primary() is None
    assert attention.observe([GazeTarget(0.0, 0.0, 0.9)]) == GazeTarget(0.0, 0.0, 0.9)


def test_validation_rejects_bad_parameters():
    with pytest.raises(ValueError):
        AttentionManager(acquire_samples=0)
    with pytest.raises(ValueError):
        AttentionManager(switch_samples=0)
    with pytest.raises(ValueError):
        AttentionManager(loss_hold_samples=0)
    with pytest.raises(ValueError):
        AttentionManager(continuity_gate=-0.1)
    with pytest.raises(ValueError):
        AttentionManager(switch_eps=-0.1)