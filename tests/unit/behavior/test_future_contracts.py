from __future__ import annotations

import pytest

from sirah.behavior.future_contracts import (
    ActionKind,
    BehaviorEvent,
    EventKind,
    ProposalResult,
    RejectionReason,
    SirahIntent,
    ValidatedAction,
)


def test_accepted_proposal_carries_a_validated_action():
    action = ValidatedAction(ActionKind.NO_OP, "shadow only")
    result = ProposalResult.accepted(action)

    assert result.action == action
    assert result.rejection is None


def test_rejected_proposal_carries_a_reason():
    result = ProposalResult.rejected(RejectionReason.SHADOW_ONLY)

    assert result.action is None
    assert result.rejection is RejectionReason.SHADOW_ONLY


def test_proposal_result_rejects_mixed_outcome():
    with pytest.raises(ValueError, match="exactly one"):
        ProposalResult(
            action=ValidatedAction(ActionKind.NO_OP, "shadow only"),
            rejection=RejectionReason.UNKNOWN_INTENT,
        )


def test_intent_is_bound_to_the_event_that_created_it():
    event = BehaviorEvent(EventKind.PERSON_ARRIVED, observed_at=1.0)
    intent = SirahIntent("greet", event)

    assert intent.event is event
