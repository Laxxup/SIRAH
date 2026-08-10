from __future__ import annotations

from sirah.behavior.attention_policy import BehaviorPolicy
from sirah.behavior.future_contracts import ActionKind, BehaviorEvent, EventKind


def test_arrival_maps_to_a_local_shadow_action():
    decision = BehaviorPolicy().decide(
        BehaviorEvent(EventKind.PERSON_ARRIVED, observed_at=1.0)
    )

    assert decision.action.kind is ActionKind.NO_OP
    assert decision.action.reason == "person_arrived"


def test_loss_maps_to_a_local_shadow_action():
    decision = BehaviorPolicy().decide(
        BehaviorEvent(EventKind.PERSON_LOST, observed_at=1.0)
    )

    assert decision.action.kind is ActionKind.NO_OP
    assert decision.action.reason == "person_lost"
