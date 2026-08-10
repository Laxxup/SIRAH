"""Validation of model proposals before a session may speak."""

from __future__ import annotations

from sirah.conversation.contracts import ActionName, IntentProposal
from sirah.conversation.errors import InvalidModelResponse


class ProposalValidator:
    """Approve only typed, non-physical proposals."""

    def validate(self, proposal: object) -> IntentProposal:
        if not isinstance(proposal, IntentProposal):
            raise InvalidModelResponse("proposer returned an invalid intent proposal")
        if proposal.action is not ActionName.NONE:
            raise InvalidModelResponse("proposal action is not approved")
        return proposal
