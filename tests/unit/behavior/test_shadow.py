from __future__ import annotations

from sirah.behavior.future_contracts import (
    ActionKind,
    BehaviorEvent,
    EventKind,
    ProposalResult,
    RejectionReason,
    ValidatedAction,
)
from sirah.behavior.shadow import ShadowLog


def test_shadow_log_preserves_accepted_and_rejected_proposals():
    log = ShadowLog()
    event = BehaviorEvent(EventKind.PERSON_ARRIVED, observed_at=1.0)
    accepted = ProposalResult.accepted(ValidatedAction(ActionKind.NO_OP, "local"))
    rejected = ProposalResult.rejected(RejectionReason.SHADOW_ONLY)

    log.record(event, accepted)
    log.record(event, rejected)

    assert log.records() == ((event, accepted), (event, rejected))
