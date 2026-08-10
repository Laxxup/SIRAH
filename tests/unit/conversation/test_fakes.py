from __future__ import annotations

import pytest

from sirah.conversation.contracts import IntentName, IntentProposal, IntentRequest
from sirah.conversation.fakes import FakeIntentProposer


async def test_fake_intent_proposer_is_offline_and_records_requests():
    proposer = FakeIntentProposer(IntentProposal(IntentName.GREET, "hola"))
    request = IntentRequest("person_arrived", "hola", 1.0)

    assert await proposer.propose(request) == IntentProposal(IntentName.GREET, "hola")
    assert proposer.requests == [request]


async def test_fake_intent_proposer_can_fail():
    proposer = FakeIntentProposer(
        IntentProposal(IntentName.SILENT, None), failure=RuntimeError("offline failure")
    )

    with pytest.raises(RuntimeError, match="offline failure"):
        await proposer.propose(IntentRequest("person_arrived", None, 1.0))
