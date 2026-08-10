"""Deterministic transcript replay metrics for conversation evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import IntentName
from sirah.conversation.session import ConversationSession


@dataclass(frozen=True)
class ConversationReplayMetrics:
    turns: int
    accepted: int
    fallback: int
    played: int
    cancelled: int


async def replay_transcripts(
    transcripts: Sequence[Transcript], session: ConversationSession
) -> ConversationReplayMetrics:
    """Replay text-only turns through a session and count observable outcomes."""
    turns = accepted = fallback = played = cancelled = 0
    for transcript in transcripts:
        turns += 1
        response = await session.respond(transcript)
        if response.proposal.intent is IntentName.SILENT:
            fallback += 1
        else:
            accepted += 1
            played += 1
    return ConversationReplayMetrics(turns, accepted, fallback, played, cancelled)
