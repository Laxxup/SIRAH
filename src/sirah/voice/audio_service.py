"""Single leased local-audio pipeline with ephemeral terminal results."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol, cast

from sirah.errors import SpeechRecognitionError, SpeechRecognitionTimeoutError
from sirah.types import SpeechRecognitionEvent, VoiceTurnResult
from sirah.voice.coordinator import AudioTurnCoordinator, AudioTurnDirection
from sirah.voice.diagnostics import (
    AudioMetrics,
    AudioStage,
    CapturedAudio,
    capture_stage,
)
from sirah.voice.port import SpeechOutputPort

__all__ = ["AudioTurnService"]


class CapturePort(Protocol):
    async def start(self) -> None: ...
    async def record(self) -> CapturedAudio: ...
    async def stop(self) -> None: ...


class SpeechRecognizer(Protocol):
    async def start(self) -> None: ...
    async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent: ...
    async def health(self) -> bool: ...
    async def stop(self) -> None: ...


class AudioTurnService:
    """Own local speech input/output while enforcing one semiduplex lease."""

    def __init__(
        self,
        *,
        capture_device: str,
        capture: CapturePort | None = None,
        capture_factory: Callable[[str], CapturePort] | None = None,
        recognizer: SpeechRecognizer | None = None,
        speech_input: object | None = None,
        speech_output: SpeechOutputPort,
        coordinator: AudioTurnCoordinator,
        respond: Callable[[str], Awaitable[str]],
    ) -> None:
        self._capture_device = capture_device
        self._capture = capture
        self._capture_factory = capture_factory
        self._recognizer = cast(SpeechRecognizer | None, recognizer or speech_input)
        self._speech_output = speech_output
        self._coordinator = coordinator
        self._respond = respond
        self._recognizer_error: SpeechRecognitionError | None = None

    async def start(self) -> None:
        """Start the persistent recognizer once without stopping the runtime on failure."""
        if self._recognizer is None:
            return
        try:
            await self._recognizer.start()
        except SpeechRecognitionTimeoutError as error:
            self._recognizer_error = error
        except Exception:
            self._recognizer_error = SpeechRecognitionError("speech recognizer unavailable")

    async def stop(self) -> None:
        if self._recognizer is not None:
            with suppress(Exception):
                await self._recognizer.stop()

    async def recognizer_healthy(self) -> bool:
        """Expose the recognizer's actual lifecycle state to the runtime."""
        return (
            self._recognizer is not None
            and self._recognizer_error is None
            and await self._recognizer.health()
        )

    async def submit_human_turn(self, timeout: float | None = None) -> VoiceTurnResult:
        """Run one human voice turn, returning a typed result on every terminal path."""
        turn_id = str(uuid.uuid4())
        try:
            lease_id = await self._coordinator.reserve_human_input()
        except Exception:
            return VoiceTurnResult(turn_id=turn_id, stage=AudioStage.CAPTURE_FAILED)

        try:
            metrics = None
            captured = CapturedAudio(b"", 16_000, 1, 2, 0, AudioMetrics(0, 0, 16_000, 1, 2, 0, 0, True))
            capture = self._capture
            if self._capture_factory is not None:
                capture = self._capture_factory(self._capture_device)
            if capture is not None:
                try:
                    await capture.start()
                    captured = await capture.record()
                    metrics = captured.metrics
                except Exception:
                    return VoiceTurnResult(turn_id=turn_id, stage=AudioStage.CAPTURE_FAILED)
                finally:
                    with suppress(Exception):
                        await capture.stop()
            if metrics is not None and (stage := capture_stage(metrics)) is not None:
                return VoiceTurnResult(turn_id=turn_id, stage=stage, diagnostics=metrics)
            if self._recognizer is None:
                return VoiceTurnResult(
                    turn_id=turn_id, stage=AudioStage.STT_EMPTY, diagnostics=metrics
                )
            try:
                if self._recognizer_error is not None:
                    raise self._recognizer_error
                recognition = await self._recognizer.transcribe(captured.data, turn_id)
            except SpeechRecognitionTimeoutError:
                return VoiceTurnResult(
                    turn_id=turn_id, stage=AudioStage.STT_TIMEOUT, diagnostics=metrics
                )
            except Exception:
                return VoiceTurnResult(
                    turn_id=turn_id, stage=AudioStage.STT_FAILED, diagnostics=metrics
                )
            if not recognition.is_final or not recognition.text.strip():
                return VoiceTurnResult(
                    turn_id=turn_id, stage=AudioStage.STT_EMPTY, diagnostics=metrics
                )

            transcript = recognition.text
            try:
                response = await self._respond(transcript)
            except Exception:
                return VoiceTurnResult(
                    turn_id=turn_id,
                    stage=AudioStage.INTELLIGENCE_FAILED,
                    diagnostics=metrics,
                    transcript=transcript,
                )

            if not await self._coordinator.transfer(lease_id, AudioTurnDirection.OUTPUT):
                return VoiceTurnResult(
                    turn_id=turn_id,
                    stage=AudioStage.TTS_FAILED,
                    diagnostics=metrics,
                    transcript=transcript,
                    response=response,
                )
            try:
                completion = await self._speech_output.speak(response)
            except Exception:
                return VoiceTurnResult(
                    turn_id=turn_id,
                    stage=AudioStage.TTS_FAILED,
                    diagnostics=metrics,
                    transcript=transcript,
                    response=response,
                )
            if not completion.success:
                return VoiceTurnResult(
                    turn_id=turn_id,
                    stage=AudioStage.PLAYBACK_FAILED,
                    diagnostics=metrics,
                    transcript=transcript,
                    response=response,
                    tts_completion=completion,
                )
            return VoiceTurnResult(
                turn_id=turn_id,
                stage=AudioStage.COMPLETED,
                diagnostics=metrics,
                transcript=transcript,
                response=response,
                tts_completion=completion,
            )
        finally:
            await self._coordinator.release(lease_id)

    async def speak_autonomously(self, text: str) -> VoiceTurnResult:
        """Speak only when no human input/output lease is held."""
        turn_id = str(uuid.uuid4())
        lease_id = await self._coordinator.reserve_autonomous_output()

        try:
            try:
                completion = await self._speech_output.speak(text)
            except Exception:
                return VoiceTurnResult(turn_id=turn_id, stage=AudioStage.TTS_FAILED)
            stage = AudioStage.COMPLETED if completion.success else AudioStage.PLAYBACK_FAILED
            return VoiceTurnResult(
                turn_id=turn_id,
                stage=stage,
                tts_completion=completion,
            )
        finally:
            await self._coordinator.release(lease_id)
