"""Policy tests (Stage 7): setpoint gate, lost-face, lab proposal gate."""

from __future__ import annotations

from sirah.runtime.policies import (
    LabProposalGate,
    LostFacePolicy,
    Setpoint,
    SetpointGate,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_setpoint_gate_accepts_contract_range():
    gate = SetpointGate()
    assert gate.validate(0.0, 0.0) == Setpoint(0.0, 0.0)
    assert gate.validate(-1.0, 1.0) == Setpoint(-1.0, 1.0)
    assert gate.rejected == 0


def test_setpoint_gate_rejects_out_of_range():
    gate = SetpointGate()
    assert gate.validate(1.5, 0.0) is None
    assert gate.validate(-0.5, -1.1) is None
    assert gate.validate(0.0, float("nan")) is None
    assert gate.rejected == 3


def test_lost_face_no_target_before_first_face():
    clock = FakeClock()
    policy = LostFacePolicy(timeout_s=2.0, clock=clock)
    for _ in range(10):
        assert policy.target() is None
    assert policy.stale()


def test_lost_face_center_after_timeout():
    clock = FakeClock()
    policy = LostFacePolicy(timeout_s=2.0, clock=clock)
    policy.on_face()
    assert policy.target() is None  # fresh, hold position
    clock.now = 101.0
    assert policy.target() is None  # within timeout
    clock.now = 102.5
    assert policy.target() == Setpoint(0.0, 0.0)
    assert policy.stale()


def test_lost_face_face_resets_timeout():
    clock = FakeClock()
    policy = LostFacePolicy(timeout_s=2.0, clock=clock)
    policy.on_face()
    clock.now = 103.0  # 3 s later — stale
    policy.on_face()  # fresh again
    clock.now = 103.5
    assert policy.target() is None  # reset held


def test_lab_gate_closed_by_default_even_when_enabled():
    gate = LabProposalGate(enabled=True)
    assert not gate.allows()
    assert gate.apply(Setpoint(0.5, 0.5)) is None


def test_lab_gate_enabled_and_open_forwards():
    gate = LabProposalGate(enabled=True)
    gate.open()
    assert gate.allows()
    assert gate.apply(Setpoint(0.3, -0.2)) == Setpoint(0.3, -0.2)


def test_lab_gate_disabled_never_forwards():
    gate = LabProposalGate(enabled=False)
    gate.open()  # even an explicit open() has no effect when lab off
    assert not gate.allows()
    assert gate.apply(Setpoint(0.3, -0.2)) is None