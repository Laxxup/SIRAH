from __future__ import annotations

import pytest

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import IntentName, IntentProposal
from sirah.conversation.coordinator import ShadowConversationCoordinator
from sirah.conversation.errors import (
    BudgetExhausted,
    ConversationTimeout,
    InvalidModelResponse,
    ProposalInFlight,
    RemoteError,
)
from sirah.conversation.fakes import FakeIntentProposer
from sirah.conversation.shadow import ShadowProposalLog


def _transcript() -> Transcript:
    return Transcript("hola sirah", started_at=1.0, ended_at=1.5, confidence=0.9)


async def test_coordinator_builds_request_and_records_valid_proposal():
    log = ShadowProposalLog()
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "hola"))
    coordinator = ShadowConversationCoordinator(proposer, log)

    result = await coordinator.handle(_transcript(), "speech_ended")

    assert result.proposal == IntentProposal(IntentName.ANSWER, "hola")
    assert result.rejection is None
    assert proposer.requests[0].event == "speech_ended"
    assert proposer.requests[0].text == "hola sirah"
    assert proposer.requests[0].observed_at == 1.5
    assert log.records()[0].proposal == result.proposal
    assert result.console_line == "proposal:answer"


@pytest.mark.parametrize(
    "failure,error_type",
    [
        (ConversationTimeout("timeout"), ConversationTimeout),
        (BudgetExhausted("budget"), BudgetExhausted),
        (ProposalInFlight("busy"), ProposalInFlight),
        (RuntimeError("network"), RemoteError),
    ],
)
async def test_coordinator_records_typed_rejection(
    failure: Exception, error_type: type[Exception]
):
    log = ShadowProposalLog()
    proposer = FakeIntentProposer(IntentProposal(IntentName.SILENT, None), failure=failure)

    result = await ShadowConversationCoordinator(proposer, log).handle(
        _transcript(), "speech_ended"
    )

    assert result.proposal is None
    assert isinstance(result.rejection, error_type)
    assert log.records()[0].rejection == result.rejection


async def test_coordinator_rejects_invalid_proposer_output():
    class InvalidProposer:
        async def propose(self, request):
            return object()

    log = ShadowProposalLog()
    result = await ShadowConversationCoordinator(InvalidProposer(), log).handle(  # type: ignore[arg-type]
        _transcript(), "speech_ended"
    )

    assert isinstance(result.rejection, InvalidModelResponse)
    assert log.records()[0].rejection == result.rejection
