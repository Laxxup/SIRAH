"""Turn-based speech responses with operation-scoped cancellation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from sirah.audio.contracts import Transcript
from sirah.conversation.context import ConversationContext
from sirah.conversation.contracts import IntentProposal, IntentProposer, IntentRequest
from sirah.conversation.personality import ConversationPersonality
from sirah.conversation.validator import ProposalValidator


class OperationTTS(Protocol):
    async def synthesize(self, operation_id: str, text: str) -> bytes: ...

    async def cancel(self, operation_id: str) -> None: ...


class OperationPCMPlayer(Protocol):
    async def play(self, operation_id: str, pcm: bytes) -> None: ...

    async def cancel(self, operation_id: str) -> None: ...


@dataclass(frozen=True)
class SessionResponse:
    operation_id: str
    proposal: IntentProposal


class ConversationSession:
    """Process one transcript at a time and cancel an obsolete response."""

    def __init__(
        self,
        proposer: IntentProposer,
        tts: OperationTTS,
        player: OperationPCMPlayer,
        *,
        context_limit: int = 8,
        validator: ProposalValidator | None = None,
        personality: ConversationPersonality | None = None,
    ) -> None:
        self._proposer = proposer
        self._tts = tts
        self._player = player
        self._validator = validator or ProposalValidator()
        self._personality = personality or ConversationPersonality()
        self.context = ConversationContext(context_limit)
        self._turn_lock = asyncio.Lock()
        self._active_task: asyncio.Task[object] | None = None
        self._active_operation: str | None = None
        self._turn_number = 0

    async def respond(self, transcript: Transcript) -> SessionResponse:
        """Generate and play the response for a transcript, if it is safe to speak."""
        await self._cancel_obsolete()
        async with self._turn_lock:
            self._turn_number += 1
            operation_id = f"conversation-{self._turn_number}"
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError("conversation sessions require an asyncio task")
            self._active_task = task
            self._active_operation = operation_id
            self.context.add(transcript)
            try:
                proposal = await self._propose_safe(transcript)
                if proposal.speech is not None:
                    pcm = await self._tts.synthesize(operation_id, proposal.speech)
                    await self._player.play(operation_id, pcm)
                return SessionResponse(operation_id, proposal)
            finally:
                if self._active_task is task:
                    self._active_task = None
                    self._active_operation = None

    async def _propose_safe(self, transcript: Transcript) -> IntentProposal:
        try:
            proposal = await self._proposer.propose(
                IntentRequest("speech_ended", transcript.text, transcript.ended_at)
            )
            return self._validator.validate(proposal)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - external proposals are untrusted; silence is safe.
            return self._personality.fallback()

    async def _cancel_obsolete(self) -> None:
        operation_id = self._active_operation
        task = self._active_task
        if operation_id is None or task is None or task is asyncio.current_task():
            return
        await self._tts.cancel(operation_id)
        await self._player.cancel(operation_id)
        task.cancel()
