from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import (
    ActionName,
    EmotionName,
    IntentName,
    IntentProposal,
)
from sirah.conversation.core import ConversationCore
from sirah.conversation.session import ConversationSession
from sirah.conversation.timing import TurnTiming


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

    async def join(self) -> None:
        return None


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


async def test_session_uses_spoken_recovery_for_malformed_proposal():
    tts = FakeTTS()
    player = FakePlayer()
    session = ConversationSession(FakeProposer(object()), tts, player)

    result = await session.respond(_transcript("hola"))

    assert result.proposal == IntentProposal(
        IntentName.CLARIFY,
        "No entendí bien, ¿puedes repetirlo?",
        EmotionName.CONCERNED,
    )
    assert tts.calls == [("conversation-1", "No entendí bien, ¿puedes repetirlo?")]
    assert player.calls == [("conversation-1", b"pcm")]


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


async def test_interrupt_cancels_the_active_response_without_starting_another_turn():
    started = asyncio.Event()

    class BlockingProposer(FakeProposer):
        async def propose(self, request):
            self.requests.append(request)
            started.set()
            await asyncio.Event().wait()

    tts = FakeTTS()
    player = FakePlayer()
    session = ConversationSession(BlockingProposer(IntentProposal(IntentName.SILENT, None)), tts, player)
    response = asyncio.create_task(session.respond(_transcript("first")))
    await started.wait()

    await session.interrupt()

    with pytest.raises(asyncio.CancelledError):
        await response
    assert tts.cancelled == ["conversation-1"]
    assert player.cancelled == ["conversation-1"]


async def test_session_uses_core_for_local_time_without_calling_ollama():
    proposer = FakeProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    session = ConversationSession(proposer, FakeTTS(), FakePlayer(), core=ConversationCore(proposer))

    result = await session.respond(_transcript("dime la hora"))

    assert result.proposal.speech is not None
    assert "Son las" in result.proposal.speech
    assert proposer.requests == []


async def test_session_notifies_turn_observer_with_transcript_and_response():
    seen = []
    transcript = _transcript("hola")
    proposal = IntentProposal(IntentName.ANSWER, "Hola")
    session = ConversationSession(FakeProposer(proposal), FakeTTS(), FakePlayer(), on_response=lambda item, reply: seen.append((item, reply)))

    await session.respond(transcript)

    assert seen == [(transcript, proposal)]


async def test_session_reports_ollama_and_tts_timings_for_a_cloud_response():
    lines: list[str] = []
    timing = TurnTiming(write=lines.append)
    proposal = IntentProposal(IntentName.ANSWER, "Hola")
    session = ConversationSession(
        FakeProposer(proposal),
        FakeTTS(),
        FakePlayer(),
        timing=timing,
    )

    await session.respond(_transcript("hola"))

    assert [line.split("] ", 1)[1].split(" |", 1)[0] for line in lines] == [
        "Ollama: iniciando",
        "Ollama: respuesta lista",
        "TTS: iniciando",
        "TTS: PCM listo",
        "Altavoz: iniciando",
        "Altavoz: reproducción terminada",
    ]


async def test_session_starts_playback_from_a_tts_pcm_stream():
    class StreamingTTS(FakeTTS):
        async def stream(self, operation_id: str, text: str) -> AsyncIterator[bytes]:
            self.calls.append((operation_id, text))
            yield b"first"
            yield b"last"

    class StreamingPlayer(FakePlayer):
        def __init__(self) -> None:
            super().__init__()
            self.stream_calls: list[tuple[str, list[bytes]]] = []

        async def play_stream(self, operation_id: str, pcm_stream: AsyncIterator[bytes]) -> None:
            self.stream_calls.append((operation_id, [chunk async for chunk in pcm_stream]))

    tts = StreamingTTS()
    player = StreamingPlayer()
    session = ConversationSession(
        FakeProposer(IntentProposal(IntentName.ANSWER, "Hola")),
        tts,
        player,
    )

    await session.respond(_transcript("hola"))

    assert tts.calls == [("conversation-1", "Hola")]
    assert player.stream_calls == [("conversation-1", [b"first", b"last"])]
    assert player.calls == []


async def test_session_recovers_from_a_rejected_proposal_without_response_text():
    diagnostics: list[str] = []

    class BrokenCore:
        async def respond(self, _transcript: Transcript) -> IntentProposal:
            raise ValueError("provider response contained private text")

    session = ConversationSession(
        FakeProposer(IntentProposal(IntentName.SILENT, None)),
        FakeTTS(),
        FakePlayer(),
        core=BrokenCore(),
        on_diagnostic=diagnostics.append,
    )

    result = await session.respond(_transcript("hola"))

    assert result.proposal == IntentProposal(
        IntentName.CLARIFY,
        "No entendí bien, ¿puedes repetirlo?",
        EmotionName.CONCERNED,
    )
    assert diagnostics == ["propuesta descartada: ValueError"]


async def test_session_marks_silent_response_before_returning_to_idle():
    lines: list[str] = []
    session = ConversationSession(
        FakeProposer(IntentProposal(IntentName.SILENT, None)),
        FakeTTS(),
        FakePlayer(),
        timing=TurnTiming(write=lines.append),
    )

    await session.respond(_transcript("hola"))

    assert [line.split("] ", 1)[1].split(" |", 1)[0] for line in lines] == [
        "Ollama: iniciando",
        "Ollama: respuesta lista",
        "Respuesta: silenciosa",
    ]
