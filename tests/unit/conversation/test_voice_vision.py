"""M8.1.3: the voice flow grounds on the SAME VisionPipeline provider.

The ordinary voice path is STT → ConversationCore → Ollama → TTS. Vision
is an opt-in provider handed to that same `ConversationCore` (exactly the
interface `vision-chat` uses); no second architecture, no duplicated
Evidence/WorldState. These tests pin: vision-free voice keeps working,
enabled vision injects FRESH context per turn, unavailable vision does not
break voice, vision never persists into turn memory, and the pipeline
shuts down cleanly alongside the voice session.
"""

from __future__ import annotations

import asyncio
import time

from sirah.audio.contracts import AudioChunk
from sirah.audio.fakes import FakeAudioSource, FakeOperationTTS, FakePCMPlayer, FakeSTT
from sirah.conversation.continuous import (
    ContinuousConversationSession,
    ContinuousSessionConfig,
    ConversationState,
)
from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal
from sirah.conversation.core import ConversationCore
from sirah.conversation.fakes import FakeIntentProposer
from sirah.conversation.session import ConversationSession
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.vision_pipeline import VisionPipeline


class FakeVAD:
    def __init__(self, speech_at: set[float]) -> None:
        self.speech_at = speech_at

    async def is_speech(self, chunk: AudioChunk, *, threshold: float | None = None) -> bool:
        return chunk.observed_at in self.speech_at


class InfiniteCamera:
    """A live camera that never ends (like /dev/video0)."""

    def __init__(self) -> None:
        self._index = 0
        self.stopped = 0

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame

    async def stop(self) -> None:
        self.stopped += 1


class FakeFaceDetector:
    def detect_many(self, frame: Frame) -> list[GazeTarget]:
        return [GazeTarget(0.2, -0.3, 0.9)]


def _proposal() -> IntentProposal:
    return IntentProposal(IntentName.ANSWER, "sí", EmotionName.FRIENDLY)


def _transcript(text: str, ended_at: float = 1.5, confidence: float = 0.9):
    from sirah.audio.contracts import Transcript

    return Transcript(text, started_at=1.0, ended_at=ended_at, confidence=confidence)


def _chunk(at: float) -> AudioChunk:
    return AudioChunk(b"pcm", 16_000, 1, at)


def _voice_session(proposer, core: ConversationCore) -> ConversationSession:
    return ConversationSession(
        proposer, FakeOperationTTS(), FakePCMPlayer(), core=core
    )


async def test_voice_conversation_works_without_vision():
    proposer = FakeIntentProposer(_proposal())
    session = _voice_session(proposer, ConversationCore(proposer))

    result = await session.respond(_transcript("¿Hay taller de robótica en el Tec?"))

    assert result.proposal.speech == "sí"
    assert proposer.requests[0].context == ()


async def test_voice_conversation_with_vision_injects_fresh_context():
    vision = "VISIÓN ACTUAL:\n- Un rostro está visible.\n- Gesto: victory."
    proposer = FakeIntentProposer(_proposal())
    session = _voice_session(
        proposer, ConversationCore(proposer, vision_context=lambda: vision)
    )

    await session.respond(_transcript("¿Qué ves?"))

    assert proposer.requests[0].context[0] == vision
    assert "Gesto: victory." in proposer.requests[0].context[0]


async def test_unavailable_vision_does_not_break_voice():
    proposer = FakeIntentProposer(_proposal())
    session = _voice_session(
        proposer, ConversationCore(proposer, vision_context=lambda: None)
    )

    result = await session.respond(_transcript("¿Qué ves?"))

    assert result.proposal.speech == "sí"
    assert proposer.requests[0].context == ()


async def test_vision_context_is_read_fresh_and_never_persists_between_turns():
    reads = 0

    def vision() -> str:
        nonlocal reads
        reads += 1
        return "VISIÓN ACTUAL:\n- Un rostro está visible."

    proposer = FakeIntentProposer(_proposal())
    session = _voice_session(
        proposer, ConversationCore(proposer, vision_context=vision)
    )

    await session.respond(_transcript("¿Qué ves?"))
    await session.respond(_transcript("¿Y ahora?"))

    # the provider is re-read on EVERY turn (fresh, never a cached block)
    assert reads == 2
    assert len(proposer.requests) == 2
    for request in proposer.requests:
        assert request.context and request.context[0].startswith("VISIÓN ACTUAL:")
        # vision is only ever the leading block; remembered turns are clean
        assert all("VISIÓN" not in item for item in request.context[1:])


async def test_voice_runs_alongside_pipeline_and_shuts_down_cleanly():
    camera = InfiniteCamera()
    pipeline = VisionPipeline(camera=camera, face_detector=FakeFaceDetector())
    await pipeline.start()
    try:
        # let the pipeline CONFIRM the face before any voice turn so the
        # injected block is deterministically grounded
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if "Un rostro está visible." in (pipeline.vision_context() or ""):
                break
            await asyncio.sleep(0)
        assert "Un rostro está visible." in (pipeline.vision_context() or "")

        proposer = FakeIntentProposer(_proposal())
        session = ContinuousConversationSession(
            FakeAudioSource([_chunk(0.0), _chunk(0.1), _chunk(0.2), _chunk(0.4)]),
            FakeVAD({0.1, 0.2}),
            FakeSTT(_transcript("hola")),
            _voice_session(
                proposer,
                ConversationCore(proposer, vision_context=pipeline.vision_context),
            ),
            config=ContinuousSessionConfig(end_silence_ms=200, min_speech_ms=50),
        )

        await session.run()

        assert session.state is ConversationState.STOPPED
        assert proposer.requests and proposer.requests[0].context
        assert "VISIÓN ACTUAL:" in proposer.requests[0].context[0]
        assert "Un rostro está visible." in proposer.requests[0].context[0]
        assert pipeline.errors == 0
    finally:
        await pipeline.stop()

    assert camera.stopped == 1