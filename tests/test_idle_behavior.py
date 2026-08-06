"""Test IdleBehavior."""

from __future__ import annotations

from sirah.autonomy.idle_behavior import IdleAction, IdleBehavior, IdleState


def test_idle_state_not_idle_initially() -> None:
    state = IdleState(idle_threshold_s=60)
    assert not state.is_idle


def test_idle_state_marks_interaction() -> None:
    state = IdleState(idle_threshold_s=1.0)
    state.mark_interaction()
    assert not state.is_idle


def test_idle_state_next_action_none_when_active() -> None:
    state = IdleState(idle_threshold_s=3600)
    assert state.next_action() is None


def test_idle_state_returns_ambient_comment() -> None:
    state = IdleState(idle_threshold_s=0.0)
    action = state.next_action()
    assert action == IdleAction.AMBIENT_COMMENT


def test_idle_state_comment_rotation() -> None:
    state = IdleState(idle_threshold_s=0.0)
    c1 = state.get_comment()
    c2 = state.get_comment()
    assert c1 != c2


def test_idle_behavior_tick_active() -> None:
    ib = IdleBehavior(idle_threshold_s=3600)
    result = ib.tick()
    assert result is None


def test_idle_behavior_tick_idle() -> None:
    ib = IdleBehavior(idle_threshold_s=0.0)
    result = ib.tick()
    assert result is not None
    action, text = result
    assert action == IdleAction.AMBIENT_COMMENT
    assert len(text) > 0


def test_idle_behavior_mark_active_resets() -> None:
    ib = IdleBehavior(idle_threshold_s=1.0)
    ib.mark_active()
    assert not ib.is_idle


def test_idle_behavior_reset() -> None:
    ib = IdleBehavior(idle_threshold_s=0.0)
    ib.tick()
    assert len(ib.history) == 1
    ib.reset()
    assert len(ib.history) == 0


def test_idle_behavior_cooldown() -> None:
    ib = IdleBehavior(idle_threshold_s=0.0)
    r1 = ib.tick()
    r2 = ib.tick()
    assert r1 is not None
    assert r2 is None
