from __future__ import annotations

import asyncio

import pytest

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import (
    ActionName,
    EmotionName,
    IntentName,
    IntentProposal,
)
from sirah.conversation.session import ConversationSession


class FakeProposer:
    def __init__(self, proposal: object) -> None:
        self.proposal = proposal
        self.requests = []

    async def propose(self, request):
        self.requests.append(request)
        return self.proposal


class FakeTTS:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.cancelled: list[str] = []

    async def synthesize(self, operation_id: str, text: str) -> bytes:
        self.calls.append((operation_id, text))
        return b"pcm"

    async def cancel(self, operation_id: str) -> None:
        self.cancelled.append(operation_id)


class FakePlayer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes]] = []
        self.cancelled: list[str] = []

    async def play(self, operation_id: str, pcm: bytes) -> None:
        self.calls.append((operation_id, pcm))

    async def cancel(self, operation_id: str) -> None:
        self.cancelled.append(operation_id)


def _transcript(text: str, ended_at: float = 1.5) -> Transcript:
    return Transcript(text, started_at=1.0, ended_at=ended_at, confidence=0.9)


async def test_session_plays_accepted_none_action_response_under_its_operation_id():
    proposer = FakeProposer(
        IntentProposal(IntentName.ANSWER, "Hola", EmotionName.FRIENDLY, ActionName.NONE)
    )
    tts = FakeTTS()
    player = FakePlayer()
    session = ConversationSession(proposer, tts, player)

    result = await session.respond(_transcript("hola"))

    assert result.proposal == proposer.proposal
    assert result.operation_id == "conversation-1"
    assert proposer.requests[0].text == "hola"
    assert tts.calls == [("conversation-1", "Hola")]
    assert player.calls == [("conversation-1", b"pcm")]


async def test_session_uses_safe_silence_for_malformed_proposal():
    tts = FakeTTS()
    player = FakePlayer()
    session = ConversationSession(FakeProposer(object()), tts, player)

    result = await session.respond(_transcript("hola"))

    assert result.proposal == IntentProposal(IntentName.SILENT, None)
    assert tts.calls == []
    assert player.calls == []


async def test_session_keeps_only_the_configured_number_of_transcripts():
    session = ConversationSession(
        FakeProposer(IntentProposal(IntentName.SILENT, None)),
        FakeTTS(),
        FakePlayer(),
        context_limit=2,
    )

    await session.respond(_transcript("first", 1.5))
    await session.respond(_transcript("second", 2.5))
    await session.respond(_transcript("third", 3.5))

    assert [transcript.text for transcript in session.context.transcripts] == ["second", "third"]


async def test_new_turn_cancels_an_obsolete_response_before_starting_its_own():
    started = asyncio.Event()

    class BlockingProposer(FakeProposer):
        async def propose(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                started.set()
                await asyncio.Event().wait()
            return IntentProposal(IntentName.SILENT, None)

    tts = FakeTTS()
    player = FakePlayer()
    session = ConversationSession(BlockingProposer(IntentProposal(IntentName.SILENT, None)), tts, player)
    obsolete = asyncio.create_task(session.respond(_transcript("first")))
    await started.wait()

    current = await session.respond(_transcript("second", 2.5))

    with pytest.raises(asyncio.CancelledError):
        await obsolete
    assert current.operation_id == "conversation-2"
    assert tts.cancelled == ["conversation-1"]
    assert player.cancelled == ["conversation-1"]
