"""In-memory records for proposals that are never executed here."""

from __future__ import annotations

from dataclasses import dataclass

from sirah.conversation.contracts import IntentProposal, IntentRequest


@dataclass(frozen=True)
class ShadowRecord:
    request: IntentRequest
    proposal: IntentProposal | None = None
    rejection: Exception | None = None


class ShadowProposalLog:
    def __init__(self) -> None:
        self._records: list[ShadowRecord] = []

    def record_proposal(self, request: IntentRequest, proposal: IntentProposal) -> None:
        self._records.append(ShadowRecord(request, proposal=proposal))

    def record_rejection(self, request: IntentRequest, rejection: Exception) -> None:
        self._records.append(ShadowRecord(request, rejection=rejection))

    def records(self) -> tuple[ShadowRecord, ...]:
        return tuple(self._records)
