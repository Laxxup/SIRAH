"""ExponentialSmoother tests (Stage 8): jump-on-first, EMA convergence,
snap-to-target, reset semantics."""

from __future__ import annotations

import pytest

from sirah.behavior.smooth import ExponentialSmoother


def test_first_sample_jumps_to_target():
    smoother = ExponentialSmoother()
    assert smoother.update(0.6, -0.4) == (0.6, -0.4)


def test_ema_converges_toward_target():
    smoother = ExponentialSmoother(alpha=0.5)
    smoother.update(1.0, 1.0)
    x, y = smoother.update(0.0, 0.0)
    assert x == pytest.approx(0.5)
    assert y == pytest.approx(0.5)
    x, y = smoother.update(0.0, 0.0)
    assert x == pytest.approx(0.25)
    assert y == pytest.approx(0.25)


def test_snaps_when_close_to_target():
    smoother = ExponentialSmoother(alpha=0.5, snap_eps=0.001)
    smoother.update(0.0, 0.0)
    x, y = smoother.update(0.0004, -0.0004)
    assert (x, y) == (0.0004, -0.0004)  # within eps of target: exact


def test_reset_makes_next_sample_jump_again():
    smoother = ExponentialSmoother()
    smoother.update(0.0, 0.0)
    assert smoother.update(1.0, 1.0) == (0.5, 0.5)
    assert smoother.update(1.0, 1.0) == (0.75, 0.75)
    smoother.reset()
    assert smoother.update(1.0, 1.0) == (1.0, 1.0)


def test_invalid_alpha_rejected():
    with pytest.raises(ValueError):
        ExponentialSmoother(alpha=0.0)
    with pytest.raises(ValueError):
        ExponentialSmoother(alpha=1.5)