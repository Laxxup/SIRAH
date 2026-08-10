from __future__ import annotations

from sirah.conversation.contracts import IntentName, IntentProposal, IntentRequest
from sirah.conversation.errors import BudgetExhausted
from sirah.conversation.shadow import ShadowProposalLog


def test_shadow_log_records_proposals_and_rejections_without_execution():
    log = ShadowProposalLog()
    request = IntentRequest("person_arrived", "hola", 1.0)
    proposal = IntentProposal(IntentName.GREET, "hola")

    log.record_proposal(request, proposal)
    log.record_rejection(request, BudgetExhausted("limit"))

    assert log.records()[0].proposal == proposal
    assert isinstance(log.records()[1].rejection, BudgetExhausted)
