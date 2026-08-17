"""EyeArbiter tests (M8): deterministic claim priority and yields."""

from __future__ import annotations

import pytest

from sirah.runtime.arbiter import EyeArbiter, Producer
from sirah.runtime.policies import Setpoint


def _sp(x: float, y: float) -> Setpoint:
    return Setpoint(x, y)


def test_highest_priority_claim_wins():
    arbiter = EyeArbiter()
    claim = arbiter.arbitrate(
        {
            Producer.SAFETY: None,
            Producer.MANUAL: _sp(0.9, -0.9),
            Producer.FACE_TRACKING: _sp(0.2, -0.2),
        },
        now=1.0,
    )
    assert claim is not None
    assert claim.producer == Producer.MANUAL
    assert claim.setpoint == _sp(0.9, -0.9)
    assert claim.acquired_at == 1.0


def test_safety_overrides_everything():
    arbiter = EyeArbiter()
    claim = arbiter.arbitrate(
        {
            Producer.SAFETY: _sp(0.0, 0.0),
            Producer.MANUAL: _sp(0.9, -0.9),
            Producer.FACE_TRACKING: _sp(0.2, -0.2),
        },
        now=1.0,
    )
    assert claim is not None
    assert claim.producer == Producer.SAFETY


def test_all_yielding_returns_none():
    arbiter = EyeArbiter()
    assert (
        arbiter.arbitrate(
            {Producer.SAFETY: None, Producer.MANUAL: None, Producer.FACE_TRACKING: None},
            now=1.0,
        )
        is None
    )


def test_empty_claims_return_none():
    arbiter = EyeArbiter()
    assert arbiter.arbitrate({}, now=1.0) is None


def test_manual_release_returns_control_to_face_tracking():
    arbiter = EyeArbiter()
    claims = {Producer.MANUAL: _sp(0.9, -0.9), Producer.FACE_TRACKING: _sp(0.2, -0.2)}
    assert arbiter.arbitrate(claims, now=1.0).producer == Producer.MANUAL
    claims[Producer.MANUAL] = None  # operator released the eyes
    assert arbiter.arbitrate(claims, now=1.1).producer == Producer.FACE_TRACKING


def test_unlisted_producer_is_arbitrated_after_priorities():
    arbiter = EyeArbiter(priorities=(Producer.SAFETY, Producer.MANUAL))
    claim = arbiter.arbitrate(
        {Producer.SAFETY: None, "expression": _sp(-0.1, 0.1), Producer.MANUAL: None},
        now=1.0,
    )
    assert claim is not None
    assert claim.producer == "expression"


def test_validation_rejects_bad_priorities():
    with pytest.raises(ValueError):
        EyeArbiter(priorities=())
    with pytest.raises(ValueError):
        EyeArbiter(priorities=(Producer.SAFETY, Producer.SAFETY))
    with pytest.raises(ValueError):
        EyeArbiter(priorities=("", "manual"))


def test_arbitrate_rejects_non_finite_clock():
    arbiter = EyeArbiter()
    with pytest.raises(ValueError):
        arbiter.arbitrate({Producer.FACE_TRACKING: _sp(0.0, 0.0)}, now=float("nan"))