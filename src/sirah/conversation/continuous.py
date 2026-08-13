"""Single-owner, hands-free conversation session driven by local VAD."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from sirah.audio.contracts import AudioChunk, AudioSource, SpeechToText, Transcript
from sirah.conversation.timing import TurnTiming


class ConversationState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    INTERRUPTING = "INTERRUPTING"
    RECOVERING = "RECOVERING"
    STOPPED = "STOPPED"


class VoiceActivity(Protocol):
    async def is_speech(self, chunk: AudioChunk, *, threshold: float | None = None) -> bool: ...


class TranscriptResponder(Protocol):
    async def respond(self, transcript: Transcript) -> object: ...

    async def interrupt(self) -> None: ...


@dataclass(frozen=True)
class ContinuousSessionConfig:
    threshold: float = 0.5
    min_speech_ms: int = 250
    end_silence_ms: int = 700
    max_turn_seconds: float = 15.0
    pre_roll_ms: int = 300
    # At 16 kHz / 512 frames, 512 chunks retain 16.384 seconds of a turn.
    max_queue_chunks: int = 512
    barge_in_threshold: float = 0.75
    barge_in_min_speech_ms: int = 200
    barge_in: bool = False
    post_playback_guard_ms: int = 500

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0 or not 0.0 <= self.barge_in_threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        if min(self.min_speech_ms, self.end_silence_ms, self.pre_roll_ms, self.barge_in_min_speech_ms, self.post_playback_guard_ms) < 0:
            raise ValueError("VAD durations must be non-negative")
        if self.max_turn_seconds <= 0:
            raise ValueError("max_turn_seconds must be positive")
        if self.max_queue_chunks <= 0:
            raise ValueError("max_queue_chunks must be positive")


class ContinuousConversationSession:
    """Run a bounded local capture loop and submit only completed speech turns.

    The oldest buffered chunk is discarded on overflow. This avoids unbounded
    memory growth while preserving the most recent speech and preroll.
    """

    def __init__(
        self,
        source: AudioSource,
        vad: VoiceActivity,
        stt: SpeechToText,
        conversation: TranscriptResponder,
        *,
        config: ContinuousSessionConfig | None = None,
        clock: Callable[[], float] | None = None,
        on_state_change: Callable[[ConversationState], Awaitable[None] | None] | None = None,
        on_error: Callable[[Exception], Awaitable[None] | None] | None = None,
        timing: TurnTiming | None = None,
        stt_label: str = "STT",
    ) -> None:
        self._source = source
        self._vad = vad
        self._stt = stt
        self._conversation = conversation
        self._config = config or ContinuousSessionConfig()
        self._clock = clock
        self._on_state_change = on_state_change
        self._on_error = on_error
        self._timing = timing
        self._stt_label = stt_label
        self._state = ConversationState.IDLE
        self._transitions = [self._state]
        self._preroll: deque[AudioChunk] = deque(maxlen=self._config.max_queue_chunks)
        self._turn: deque[AudioChunk] = deque(maxlen=self._config.max_queue_chunks)
        self._speech_started_at: float | None = None
        self._last_speech_at: float | None = None
        self._barge_started_at: float | None = None
        self._started = False
        self._generation = 0
        self._processing_task: asyncio.Task[None] | None = None
        self._now = clock or time.monotonic
        self._guard_until = 0.0

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def transitions(self) -> tuple[ConversationState, ...]:
        return tuple(self._transitions)

    @property
    def buffered_chunks(self) -> int:
        return len(self._preroll) + len(self._turn)

    async def start(self) -> None:
        if self._started:
            return
        await self._source.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started and self._state is ConversationState.STOPPED:
            return
        self._generation += 1
        await self._cancel_processing()
        self._clear_buffers()
        if self._started:
            await self._source.stop()
            self._started = False
        await self._set_state(ConversationState.STOPPED)

    async def run(self) -> None:
        try:
            await self.start()
            while True:
                chunk = await self._source.next_chunk()
                if chunk is None:
                    if self._state is ConversationState.LISTENING:
                        await self._close_turn()
                    if self._processing_task is not None:
                        await self._processing_task
                    return
                await self._handle_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - capture providers are external.
            await self._report_error(exc)
            await self._set_state(ConversationState.RECOVERING)
        finally:
            await self.stop()

    async def _handle_chunk(self, chunk: AudioChunk) -> None:
        if self._state is ConversationState.SPEAKING:
            if not self._config.barge_in:
                self._clear_buffers()
                return
            speech = await self._vad.is_speech(chunk, threshold=self._config.barge_in_threshold)
            self._append_preroll(chunk)
            if speech and self._barge_started_at is None:
                self._barge_started_at = chunk.observed_at
                return
            barge_started_at = self._barge_started_at
            if speech and barge_started_at is not None and (chunk.observed_at - barge_started_at) * 1000 >= self._config.barge_in_min_speech_ms:
                await self._interrupt_for_new_voice(chunk)
            elif not speech:
                self._barge_started_at = None
            return
        speech = await self._vad.is_speech(chunk, threshold=self._config.threshold)
        if self._now() < self._guard_until:
            self._clear_buffers()
            return
        if self._state is ConversationState.PROCESSING:
            if not self._config.barge_in:
                self._clear_buffers()
                return
            self._append_preroll(chunk)
            if speech:
                await self._interrupt_for_new_voice(chunk)
            return
        if self._state is ConversationState.INTERRUPTING:
            return
        if self._state is ConversationState.STOPPED:
            return
        if self._state is ConversationState.IDLE:
            self._append_preroll(chunk)
            if speech:
                self._turn.extend(self._preroll)
                self._speech_started_at = chunk.observed_at
                self._last_speech_at = chunk.observed_at
                await self._set_state(ConversationState.LISTENING)
            return
        if self._state is not ConversationState.LISTENING:
            return
        self._append_turn(chunk)
        if speech:
            self._last_speech_at = chunk.observed_at
        if self._speech_started_at is None or self._last_speech_at is None:
            return
        elapsed = chunk.observed_at - self._speech_started_at
        silence = chunk.observed_at - self._last_speech_at
        if elapsed >= self._config.max_turn_seconds or silence * 1000 >= self._config.end_silence_ms:
            await self._close_turn()

    async def _interrupt_for_new_voice(self, chunk: AudioChunk) -> None:
        self._barge_started_at = None
        await self._set_state(ConversationState.INTERRUPTING)
        self._generation += 1
        await self._cancel_processing()
        await self._conversation.interrupt()
        self._turn.extend(self._preroll)
        self._speech_started_at = chunk.observed_at
        self._last_speech_at = chunk.observed_at
        await self._set_state(ConversationState.LISTENING)

    async def _close_turn(self) -> None:
        generation = self._generation = self._generation + 1
        chunks = tuple(self._turn)
        speech_started_at = self._speech_started_at
        last_speech_at = self._last_speech_at
        self._clear_buffers()
        if not chunks or speech_started_at is None or last_speech_at is None:
            await self._set_state(ConversationState.IDLE)
            return
        speech_ms = (last_speech_at - speech_started_at) * 1000
        if speech_ms < self._config.min_speech_ms:
            await self._set_state(ConversationState.IDLE)
            return
        if self._timing is not None:
            self._timing.reset()
            self._timing.mark("Fin de voz detectado")
        await self._set_state(ConversationState.PROCESSING)
        self._processing_task = asyncio.create_task(self._process_turn(generation, chunks))
        # Give the task one scheduling point so capture can continue while it waits on I/O.
        await asyncio.sleep(0)

    async def _process_turn(self, generation: int, chunks: Sequence[AudioChunk]) -> None:
        try:
            self._mark(f"{self._stt_label}: iniciando")
            transcript = await self._stt.transcribe(chunks)
            self._mark(f"{self._stt_label}: listo")
            if generation != self._generation or not transcript.text.strip():
                return
            await self._set_state(ConversationState.SPEAKING)
            await self._conversation.respond(transcript)
            reset = getattr(self._vad, "reset", None)
            if reset is not None:
                await reset()
            self._guard_until = self._now() + self._config.post_playback_guard_ms / 1000
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - failures enter a visible recovery state.
            await self._report_error(exc)
            await self._set_state(ConversationState.RECOVERING)
        finally:
            if generation == self._generation and self._state is not ConversationState.RECOVERING:
                await self._set_state(ConversationState.IDLE)

    async def _cancel_processing(self) -> None:
        task = self._processing_task
        self._processing_task = None
        if task is None or task is asyncio.current_task() or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _append_preroll(self, chunk: AudioChunk) -> None:
        self._preroll.append(chunk)
        cutoff = chunk.observed_at - self._config.pre_roll_ms / 1000
        while self._preroll and self._preroll[0].observed_at < cutoff:
            self._preroll.popleft()

    def _append_turn(self, chunk: AudioChunk) -> None:
        self._turn.append(chunk)

    def _clear_buffers(self) -> None:
        self._preroll.clear()
        self._turn.clear()
        self._speech_started_at = None
        self._last_speech_at = None

    async def _set_state(self, state: ConversationState) -> None:
        if state is self._state:
            return
        self._state = state
        self._transitions.append(state)
        if self._on_state_change is not None:
            result = self._on_state_change(state)
            if result is not None:
                await result

    async def _report_error(self, error: Exception) -> None:
        if self._on_error is None:
            return
        result = self._on_error(error)
        if result is not None:
            await result

    def _mark(self, label: str) -> None:
        if self._timing is not None:
            self._timing.mark(label)
