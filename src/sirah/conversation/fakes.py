"""Offline conversation double with no network or model dependency."""

from __future__ import annotations

from sirah.conversation.contracts import IntentProposal, IntentRequest


class FakeIntentProposer:
    def __init__(self, proposal: IntentProposal, *, failure: Exception | None = None) -> None:
        self._proposal = proposal
        self._failure = failure
        self.requests: list[IntentRequest] = []

    async def propose(self, request: IntentRequest) -> IntentProposal:
        self.requests.append(request)
        if self._failure is not None:
            raise self._failure
        return self._proposal
