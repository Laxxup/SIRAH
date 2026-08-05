"""Whisper STT — local speech-to-text via faster-whisper."""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any

from sirah.types import SpeechRecognitionEvent
from sirah.errors import SpeechInputError, SpeechUnavailableError

__all__ = ["WhisperSTT"]

logger = logging.getLogger(__name__)


class WhisperSTT:
    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "es",
        beam_size: int = 5,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._beam_size = beam_size
        self._model: Any = None
        self._initialised = False

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._model = await loop.run_in_executor(None, self._load_model)
        self._initialised = True
        logger.info("WhisperSTT: model %s loaded", self._model_size)

    async def stop(self) -> None:
        self._model = None
        self._initialised = False

    async def health(self) -> bool:
        return self._initialised and self._model is not None

    def _load_model(self) -> Any:
        from faster_whisper import WhisperModel

        return WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )

    async def transcribe(self, audio_data: bytes) -> SpeechRecognitionEvent:
        if not self._initialised or self._model is None:
            raise SpeechUnavailableError("Whisper model not loaded")

        loop = asyncio.get_running_loop()
        t0 = monotonic()

        try:
            def _run() -> SpeechRecognitionEvent:
                import numpy as np
                import io
                import wave

                buf = io.BytesIO(audio_data)
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

            result = await loop.run_in_executor(None, _run)
            latency = (monotonic() - t0) * 1000
            logger.debug("Whisper transcribed in %.0fms: %s", latency, result.text[:80])
            return result

        except Exception as exc:
            raise SpeechInputError(f"Whisper transcription failed: {exc}") from exc
