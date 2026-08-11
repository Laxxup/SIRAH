from __future__ import annotations

import asyncio

from sirah.audio.contracts import AudioChunk, Transcript
from sirah.conversation.continuous import (
    ContinuousConversationSession,
    ContinuousSessionConfig,
    ConversationState,
)


def _chunk(at: float) -> AudioChunk:
    return AudioChunk(b"pcm", 16_000, 1, at)


class FakeVAD:
    def __init__(self, speech_at: set[float]) -> None:
        self.speech_at = speech_at
        self.calls: list[AudioChunk] = []

    async def is_speech(self, chunk: AudioChunk, *, threshold: float | None = None) -> bool:
        self.calls.append(chunk)
        return chunk.observed_at in self.speech_at


class FakeSource:
    def __init__(self, chunks: list[AudioChunk], *, failure: Exception | None = None) -> None:
        self.chunks = chunks
        self.failure = failure
        self.started = 0
        self.stopped = 0

    async def start(self) -> None:
        self.started += 1

    async def next_chunk(self) -> AudioChunk | None:
        if self.failure is not None:
            raise self.failure
        return self.chunks.pop(0) if self.chunks else None

    async def stop(self) -> None:
        self.stopped += 1


class FakeSTT:
    def __init__(self, texts: list[str], *, failure: Exception | None = None) -> None:
        self.texts = texts
        self.failure = failure
        self.requests: list[tuple[AudioChunk, ...]] = []

    async def transcribe(self, chunks: list[AudioChunk]) -> Transcript:
        self.requests.append(tuple(chunks))
        if self.failure is not None:
            raise self.failure
        text = self.texts.pop(0)
        return Transcript(text, chunks[0].observed_at, chunks[-1].observed_at, 0.9)


class FakeConversation:
    def __init__(self) -> None:
        self.requests: list[Transcript] = []
        self.started = asyncio.Event()
        self.block = False
        self.interruptions = 0

    async def respond(self, transcript: Transcript) -> None:
        self.requests.append(transcript)
        self.started.set()
        if self.block:
            await asyncio.Event().wait()

    async def interrupt(self) -> None:
        self.interruptions += 1



async def test_closes_speech_after_silence_then_transcribes_once():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.2), _chunk(0.4)])
    stt = FakeSTT(["hola"])
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.2}),
        stt,
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=50),
    )

    await session.run()

    assert len(stt.requests) == 1
    assert [request.text for request in conversation.requests] == ["hola"]
    assert session.state is ConversationState.STOPPED
    assert ConversationState.LISTENING in session.transitions
    assert ConversationState.PROCESSING in session.transitions


async def test_ignores_brief_noise_without_stt_or_cloud_request():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4)])
    stt = FakeSTT(["should not be used"])
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1}),
        stt,
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=150),
    )

    await session.run()

    assert stt.requests == []
    assert conversation.requests == []


async def test_includes_bounded_pre_roll_when_speech_starts():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.2), _chunk(0.5)])
    stt = FakeSTT(["hola"])
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.2}),
        stt,
        FakeConversation(),
        config=ContinuousSessionConfig(pre_roll_ms=150, end_silence_ms=200, min_speech_ms=0),
    )

    await session.run()

    assert [chunk.observed_at for chunk in stt.requests[0]] == [0.1, 0.2, 0.5]


async def test_rejects_empty_final_transcript_before_cloud_request():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4)])
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1}),
        FakeSTT(["   "]),
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0, barge_in_min_speech_ms=0),
    )

    await session.run()

    assert conversation.requests == []


async def test_maximum_turn_duration_closes_without_waiting_for_silence():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.3), _chunk(0.6)])
    stt = FakeSTT(["larga"])
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.3, 0.6}),
        stt,
        FakeConversation(),
        config=ContinuousSessionConfig(max_turn_seconds=0.4, min_speech_ms=0),
    )

    await session.run()

    assert len(stt.requests) == 1
    assert stt.requests[0][-1].observed_at == 0.6


async def test_processes_consecutive_turns_without_keyboard_input():
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4), _chunk(0.5), _chunk(0.8)])
    stt = FakeSTT(["uno", "dos"])
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.5}),
        stt,
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0),
    )

    await session.run()

    assert [request.text for request in conversation.requests] == ["uno", "dos"]


async def test_source_failure_recovers_then_stops_without_persisting_buffers():
    source = FakeSource([], failure=OSError("device disconnected"))
    session = ContinuousConversationSession(source, FakeVAD(set()), FakeSTT([]), FakeConversation())

    await session.run()

    assert ConversationState.RECOVERING in session.transitions
    assert session.state is ConversationState.STOPPED
    assert session.buffered_chunks == 0
    assert source.stopped == 1


async def test_source_failure_reports_the_underlying_error_to_the_operator_callback():
    errors: list[str] = []
    session = ContinuousConversationSession(
        FakeSource([], failure=OSError("invalid VAD block size")),
        FakeVAD(set()),
        FakeSTT([]),
        FakeConversation(),
        on_error=lambda error: errors.append(str(error)),
    )

    await session.run()

    assert errors == ["invalid VAD block size"]


async def test_processing_failure_reports_the_underlying_error_to_the_operator_callback():
    errors: list[str] = []
    session = ContinuousConversationSession(
        FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4)]),
        FakeVAD({0.1}),
        FakeSTT(["unused"], failure=RuntimeError("Azure rejected credentials")),
        FakeConversation(),
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0),
        on_error=lambda error: errors.append(str(error)),
    )
    await session.run()

    assert errors == ["Azure rejected credentials"]


async def test_start_and_stop_are_idempotent():
    source = FakeSource([])
    session = ContinuousConversationSession(source, FakeVAD(set()), FakeSTT([]), FakeConversation())

    await session.start()
    await session.start()
    await session.stop()
    await session.stop()

    assert source.started == 1
    assert source.stopped == 1
    assert session.state is ConversationState.STOPPED


async def test_new_voice_during_processing_invalidates_the_obsolete_turn():
    class BlockingFirstConversation(FakeConversation):
        async def respond(self, transcript: Transcript) -> None:
            self.requests.append(transcript)
            if len(self.requests) == 1:
                self.started.set()
                await asyncio.Event().wait()

    source = FakeSource(
        [_chunk(0.0), _chunk(0.1), _chunk(0.4), _chunk(0.5), _chunk(0.6), _chunk(0.9)]
    )
    conversation = BlockingFirstConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.5, 0.6}),
        FakeSTT(["first", "latest"]),
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0, barge_in_min_speech_ms=0),
    )

    await asyncio.wait_for(session.run(), timeout=0.2)

    assert [request.text for request in conversation.requests] == ["first", "latest"]
    assert conversation.interruptions == 1
    assert ConversationState.INTERRUPTING in session.transitions
