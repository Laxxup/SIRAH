"""Whisper STT — local speech-to-text via faster-whisper."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from sirah.errors import (
    SpeechRecognitionError,
    SpeechRecognitionTimeoutError,
    SpeechUnavailableError,
)
from sirah.types import SpeechRecognitionEvent

__all__ = ["SttDiagnostics", "WhisperSTT"]


@dataclass(frozen=True, slots=True)
class SttDiagnostics:
    """Transcript-free timing for one ephemeral recognizer turn."""

    turn_id: str
    latency_ms: float


class WhisperSTT:
    def __init__(
        self,
        model_size: str = "tiny",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "es",
        beam_size: int = 1,
        timeout_s: float = 30.0,
        model_loader: Callable[[], Any] | None = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._timeout_s = timeout_s
        self._model_loader = model_loader
        self._model: Any = None
        self._initialised = False
        self._load_error: SpeechUnavailableError | None = None
        self._start_lock = asyncio.Lock()
        self._diagnostics: OrderedDict[str, SttDiagnostics] = OrderedDict()

    async def start(self) -> None:
        async with self._start_lock:
            if self._initialised:
                return
            if self._load_error is not None:
                raise self._load_error
            try:
                loop = asyncio.get_running_loop()
                self._model = await loop.run_in_executor(None, self._load_model)
            except Exception as error:
                self._load_error = SpeechUnavailableError("Whisper model could not load")
                raise self._load_error from error
            self._initialised = True

    async def stop(self) -> None:
        self._model = None
        self._initialised = False

    async def health(self) -> bool:
        return self._initialised and self._model is not None

    def _load_model(self) -> Any:
        if self._model_loader is not None:
            return self._model_loader()
        from faster_whisper import WhisperModel

        return WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )

    async def transcribe(self, wav: bytes, turn_id: str) -> SpeechRecognitionEvent:
        if not self._initialised or self._model is None:
            if self._load_error is not None:
                raise self._load_error
            raise SpeechUnavailableError("Whisper model not loaded")

        loop = asyncio.get_running_loop()
        t0 = monotonic()

        try:
            def _run() -> SpeechRecognitionEvent:
                import io
                import wave

                import numpy as np

                buf = io.BytesIO(wav)
                with wave.open(buf, "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

                segments, _ = self._model.transcribe(  # type: ignore[union-attr]
                    audio_np,
                    language=self._language,
                    beam_size=self._beam_size,
                )

                text_parts: list[str] = []
                confidence_sum = 0.0
                count = 0
                for seg in segments:
                    text_parts.append(seg.text)
                    confidence_sum += seg.avg_logprob
                    count += 1

                full_text = " ".join(text_parts).strip()
                avg_conf = (
                    min(1.0, max(0.0, (confidence_sum / count + 1.0) / 2.0))
                    if count > 0
                    else 0.0
                )
                return SpeechRecognitionEvent(
                    text=full_text,
                    is_final=bool(full_text),
                    confidence=avg_conf,
                    timestamp=monotonic(),
                )

            result = await asyncio.wait_for(
                loop.run_in_executor(None, _run), timeout=self._timeout_s
            )
            self._record_diagnostics(turn_id, (monotonic() - t0) * 1000)
            return result
        except TimeoutError as error:
            self._record_diagnostics(turn_id, (monotonic() - t0) * 1000)
            raise SpeechRecognitionTimeoutError("Whisper transcription timed out") from error
        except Exception as error:
            self._record_diagnostics(turn_id, (monotonic() - t0) * 1000)
            raise SpeechRecognitionError("Whisper transcription failed") from error

    def diagnostics_for(self, turn_id: str) -> SttDiagnostics:
        """Return bounded transcript-free timing for the requested turn."""
        return self._diagnostics[turn_id]

    def _record_diagnostics(self, turn_id: str, latency_ms: float) -> None:
        self._diagnostics[turn_id] = SttDiagnostics(turn_id, latency_ms)
        self._diagnostics.move_to_end(turn_id)
        if len(self._diagnostics) > 64:
            self._diagnostics.popitem(last=False)
