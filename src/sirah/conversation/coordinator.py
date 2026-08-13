"""Shadow-only bridge from derived transcripts to structured intent proposals."""

from __future__ import annotations

from dataclasses import dataclass

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import IntentProposal, IntentProposer, IntentRequest
from sirah.conversation.errors import (
    ConversationError,
    InvalidModelResponse,
    RemoteError,
)
from sirah.conversation.shadow import ShadowProposalLog


@dataclass(frozen=True)
class CoordinatorResult:
    request: IntentRequest
    proposal: IntentProposal | None = None
    rejection: ConversationError | None = None

    @property
    def console_line(self) -> str:
        if self.proposal is not None:
            return f"proposal:{self.proposal.intent.value}"
        assert self.rejection is not None
        return f"rejected:{type(self.rejection).__name__}"


class ShadowConversationCoordinator:
    """Coordinates proposals for observation only; it never executes an intent."""

    def __init__(self, proposer: IntentProposer, shadow_log: ShadowProposalLog) -> None:
        self._proposer = proposer
        self._shadow_log = shadow_log

    async def handle(self, transcript: Transcript, event: str) -> CoordinatorResult:
        """Build a derived-text request and record the proposal or rejection."""
        request = IntentRequest(event, transcript.text, transcript.ended_at)
        try:
            proposal = await self._proposer.propose(request)
            if not isinstance(proposal, IntentProposal):
                raise InvalidModelResponse("proposer returned an invalid intent proposal")
        except ConversationError as exc:
            self._shadow_log.record_rejection(request, exc)
            return CoordinatorResult(request, rejection=exc)
        except Exception as exc:  # noqa: BLE001 - external proposer failures are shadow rejections.
            rejection = RemoteError(str(exc))
            self._shadow_log.record_rejection(request, rejection)
            return CoordinatorResult(request, rejection=rejection)
        self._shadow_log.record_proposal(request, proposal)
        return CoordinatorResult(request, proposal=proposal)
