from __future__ import annotations

import asyncio
import json

import pytest

from sirah.audio.contracts import AudioChunk, Transcript
from sirah.audio.fakes import FakeOperationTTS, FakePCMPlayer
from sirah.conversation.continuous import (
    ContinuousConversationSession,
    ContinuousSessionConfig,
    ConversationState,
)
from sirah.conversation.ollama import OllamaIntentProposer
from sirah.conversation.session import ConversationSession
from sirah.conversation.timing import TurnTiming


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
        self.calls = 0

    async def start(self) -> None:
        self.started += 1

    async def next_chunk(self) -> AudioChunk | None:
        self.calls += 1
        if self.failure is not None:
            failure, self.failure = self.failure, None
            raise failure
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
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0, post_playback_guard_ms=0),
    )

    await session.run()

    assert [request.text for request in conversation.requests] == ["uno", "dos"]


async def test_source_failure_recovers_then_stops_without_persisting_buffers():
    source = FakeSource([], failure=OSError("device disconnected"))
    session = ContinuousConversationSession(
        source,
        FakeVAD(set()),
        FakeSTT([]),
        FakeConversation(),
        config=ContinuousSessionConfig(recovery_delay_ms=0),
    )

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
        config=ContinuousSessionConfig(recovery_delay_ms=0),
        on_error=lambda error: errors.append(str(error)),
    )

    await session.run()

    assert errors == ["invalid VAD block size"]


async def test_transient_source_failure_does_not_retry_before_recovery_delay_elapses():
    class FixedClock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = FixedClock()
    source = FakeSource([], failure=OSError("device disconnected"))
    session = ContinuousConversationSession(
        source,
        FakeVAD(set()),
        FakeSTT([]),
        FakeConversation(),
        config=ContinuousSessionConfig(recovery_delay_ms=1_000),
        clock=clock,
    )

    run = asyncio.create_task(session.run())
    for _ in range(200):
        if session.state is ConversationState.RECOVERING:
            break
        await asyncio.sleep(0.01)

    assert session.state is ConversationState.RECOVERING
    assert session._recovering_until == 1.0
    assert source.calls == 1
    assert session.transitions.count(ConversationState.RECOVERING) == 1

    await asyncio.sleep(0.05)
    assert source.calls == 1

    clock.now = 1.0
    await asyncio.wait_for(run, timeout=1.0)

    assert source.calls == 2
    assert session.state is ConversationState.STOPPED


async def test_config_rejects_negative_max_recovery_attempts():
    with pytest.raises(ValueError, match="max_recovery_attempts"):
        ContinuousSessionConfig(max_recovery_attempts=-1)


async def test_persistent_source_failure_stops_after_max_recovery_attempts():
    class AlwaysFailingSource:
        def __init__(self) -> None:
            self.calls = 0
            self.started = 0
            self.stopped = 0

        async def start(self) -> None:
            self.started += 1

        async def next_chunk(self) -> AudioChunk | None:
            self.calls += 1
            raise OSError("device disconnected")

        async def stop(self) -> None:
            self.stopped += 1

    errors: list[str] = []
    source = AlwaysFailingSource()
    session = ContinuousConversationSession(
        source,
        FakeVAD(set()),
        FakeSTT([]),
        FakeConversation(),
        config=ContinuousSessionConfig(recovery_delay_ms=0, max_recovery_attempts=3),
        on_error=lambda error: errors.append(str(error)),
    )

    await asyncio.wait_for(session.run(), timeout=1.0)

    assert source.calls == 4
    assert errors == ["device disconnected"] * 4
    assert ConversationState.RECOVERING in session.transitions
    assert session.state is ConversationState.STOPPED
    assert source.stopped == 1


async def test_recovery_attempts_reset_after_success_then_bounds_again():
    class FlakySource:
        def __init__(self) -> None:
            self.calls = 0
            self.started = 0
            self.stopped = 0
            self.chunks = [_chunk(0.0)]
            self.failed_once = False

        async def start(self) -> None:
            self.started += 1

        async def next_chunk(self) -> AudioChunk | None:
            self.calls += 1
            if not self.failed_once:
                self.failed_once = True
                raise OSError("device disconnected")
            if self.chunks:
                return self.chunks.pop(0)
            raise OSError("device disconnected")

        async def stop(self) -> None:
            self.stopped += 1

    errors: list[str] = []
    source = FlakySource()
    session = ContinuousConversationSession(
        source,
        FakeVAD(set()),
        FakeSTT([]),
        FakeConversation(),
        config=ContinuousSessionConfig(recovery_delay_ms=0, max_recovery_attempts=3),
        on_error=lambda error: errors.append(str(error)),
    )

    await asyncio.wait_for(session.run(), timeout=1.0)

    assert source.calls == 6
    assert len(errors) == 5
    assert session.state is ConversationState.STOPPED
    assert source.stopped == 1


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


async def test_recovers_to_idle_after_processing_failure_and_accepts_a_new_turn():
    class FlakySTT(FakeSTT):
        def __init__(self) -> None:
            super().__init__(["dos"], failure=RuntimeError("boom"))
            self.attempts = 0

        async def transcribe(self, chunks: list[AudioChunk]) -> Transcript:
            self.attempts += 1
            if self.failure is not None:
                failure, self.failure = self.failure, None
                raise failure
            return await super().transcribe(chunks)

    errors: list[str] = []
    source = FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4), _chunk(0.5), _chunk(0.6), _chunk(0.9)])
    stt = FlakySTT()
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.5, 0.6}),
        stt,
        conversation,
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0, recovery_delay_ms=0),
        on_error=lambda error: errors.append(str(error)),
    )

    await session.run()

    assert errors == ["boom"]
    assert stt.attempts == 2
    assert [request.text for request in conversation.requests] == ["dos"]
    recovering = session.transitions.index(ConversationState.RECOVERING)
    assert ConversationState.IDLE in session.transitions[recovering + 1:]
    assert session.state is ConversationState.STOPPED


async def test_processing_failure_drops_chunks_until_recovery_delay_elapses():
    errors: list[str] = []
    source = FakeSource(
        [_chunk(0.0), _chunk(0.1), _chunk(0.4), _chunk(0.5), _chunk(0.6)]
    )
    stt = FakeSTT(["unused"], failure=RuntimeError("boom"))
    session = ContinuousConversationSession(
        source,
        FakeVAD({0.1, 0.5, 0.6}),
        stt,
        FakeConversation(),
        config=ContinuousSessionConfig(
            end_silence_ms=200, min_speech_ms=0, recovery_delay_ms=10_000
        ),
        on_error=lambda error: errors.append(str(error)),
    )

    await session.run()

    assert errors == ["boom"]
    assert len(stt.requests) == 1
    assert session.state is ConversationState.STOPPED
    recovering = session.transitions.index(ConversationState.RECOVERING)
    assert ConversationState.IDLE not in session.transitions[recovering + 1:]
    assert session.buffered_chunks == 0


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
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0, barge_in=True, barge_in_min_speech_ms=0),
    )

    await asyncio.wait_for(session.run(), timeout=0.2)

    assert [request.text for request in conversation.requests] == ["first", "latest"]
    assert conversation.interruptions == 1
    assert ConversationState.INTERRUPTING in session.transitions


async def test_default_semiduplex_discards_microphone_frames_while_speaking():
    conversation = FakeConversation()
    session = ContinuousConversationSession(FakeSource([]), FakeVAD({1.0}), FakeSTT([]), conversation)
    await session._set_state(ConversationState.SPEAKING)

    await session._handle_chunk(_chunk(1.0))

    assert conversation.interruptions == 0
    assert session.buffered_chunks == 0


async def test_default_semiduplex_discards_microphone_frames_while_processing():
    conversation = FakeConversation()
    session = ContinuousConversationSession(FakeSource([]), FakeVAD({1.0}), FakeSTT([]), conversation)
    await session._set_state(ConversationState.PROCESSING)

    await session._handle_chunk(_chunk(1.0))

    assert conversation.interruptions == 0
    assert session.state is ConversationState.PROCESSING
    assert session.buffered_chunks == 0


async def test_barge_in_while_stt_is_still_processing_interrupts_the_turn():
    class BlockingSTT(FakeSTT):
        def __init__(self) -> None:
            super().__init__(["first"])
            self.started = asyncio.Event()

        async def transcribe(self, chunks: list[AudioChunk]) -> Transcript:
            self.started.set()
            await asyncio.Event().wait()  # STT still in flight when new voice arrives
            return Transcript("first", chunks[0].observed_at, chunks[-1].observed_at, 0.9)

    stt = BlockingSTT()
    conversation = FakeConversation()
    session = ContinuousConversationSession(
        FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4), _chunk(0.5)]),
        FakeVAD({0.1, 0.5}),
        stt,
        conversation,
        config=ContinuousSessionConfig(
            end_silence_ms=200,
            min_speech_ms=0,
            barge_in=True,
            barge_in_min_speech_ms=0,
        ),
    )
    run = asyncio.create_task(session.run())
    await stt.started.wait()  # turn closed; STT now stuck in PROCESSING
    await asyncio.sleep(0)  # let the capture loop observe a new voice chunk
    await asyncio.sleep(0)
    assert session.state is ConversationState.PROCESSING
    assert conversation.interruptions == 1
    assert ConversationState.INTERRUPTING in session.transitions
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run


async def test_session_reports_voice_end_and_stt_timing_before_the_response():
    lines: list[str] = []
    session = ContinuousConversationSession(
        FakeSource([_chunk(0.0), _chunk(0.1), _chunk(0.4)]),
        FakeVAD({0.1}),
        FakeSTT(["hola"]),
        FakeConversation(),
        config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=0),
        timing=TurnTiming(write=lines.append),
        stt_label="STT Groq",
    )

    await session.run()

    assert [line.split("] ", 1)[1].split(" |", 1)[0] for line in lines] == [
        "Fin de voz detectado",
        "STT Groq: iniciando",
        "STT Groq: listo",
    ]


async def test_retains_a_fifteen_second_turn_at_the_configured_32ms_frame_size():
    chunks = [_chunk(index * 0.032) for index in range(470)]
    stt = FakeSTT(["turno largo"])
    session = ContinuousConversationSession(
        FakeSource(chunks),
        FakeVAD({chunk.observed_at for chunk in chunks}),
        stt,
        FakeConversation(),
        config=ContinuousSessionConfig(max_turn_seconds=15, min_speech_ms=0),
    )

    await session.run()

    assert len(stt.requests) == 1
    assert len(stt.requests[0]) >= 469


async def test_hands_free_session_exceeds_ten_turns_without_budget_exhaustion():
    calls: list[bytes] = []

    async def post(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> bytes:
        calls.append(body)
        return json.dumps(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "intent": "answer",
                            "speech": "Hola, sigamos.",
                            "emotion": "friendly",
                            "action": "none",
                        }
                    )
                }
            }
        ).encode()

    proposer = OllamaIntentProposer.from_environment(
        environ={
            "SIRAH_OLLAMA_HOST": "https://offline.invalid",
            "SIRAH_OLLAMA_MODEL": "offline-model",
            "SIRAH_OLLAMA_API_KEY": "offline-key",
        },
        timeout_s=10.0,
        budget=1,
        post=post,
    )
    conversation = ConversationSession(proposer, FakeOperationTTS(), FakePCMPlayer())
    chunks: list[AudioChunk] = []
    texts: list[str] = []
    speech_at: set[float] = set()
    for turn in range(12):
        base = turn * 10
        chunks.extend([_chunk(base + 0.1), _chunk(base + 0.2), _chunk(base + 0.5)])
        speech_at.update({base + 0.1, base + 0.2})
        texts.append(f"turno {turn}")
    session = ContinuousConversationSession(
        FakeSource(chunks),
        FakeVAD(speech_at),
        FakeSTT(texts),
        conversation,
        config=ContinuousSessionConfig(
            end_silence_ms=200, min_speech_ms=0, post_playback_guard_ms=0
        ),
    )

    await session.run()

    assert session.state is ConversationState.STOPPED
    assert len(calls) == 12
