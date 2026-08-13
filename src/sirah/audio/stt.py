"""Lazy Faster-Whisper speech-to-text adapter."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from array import array
from collections.abc import Callable, Sequence
from math import exp

from sirah.audio.contracts import AudioChunk, Transcript

_ModelFactory = Callable[[str], object]


class FasterWhisperSTT:
    """Transcribe 16-bit PCM chunks without blocking the event loop."""

    def __init__(
        self,
        model_name: str,
        *,
        language: str | None = "es",
        model_factory: _ModelFactory | None = None,
    ) -> None:
        self._model_name = model_name
        self._language = language
        self._model_factory = model_factory
        self._model: object | None = None
        self._model_lock = threading.Lock()

    async def transcribe(self, chunks: Sequence[AudioChunk]) -> Transcript:
        return await asyncio.to_thread(self._transcribe, tuple(chunks))

    async def preload(self) -> None:
        """Load the model before the first spoken turn."""
        await asyncio.to_thread(self._get_model)

    def _transcribe(self, chunks: tuple[AudioChunk, ...]) -> Transcript:
        if not chunks:
            raise ValueError("at least one audio chunk is required")
        first = chunks[0]
        if any(
            chunk.sample_rate != first.sample_rate or chunk.channels != first.channels
            for chunk in chunks[1:]
        ):
            raise ValueError("all chunks must use the same sample rate and channels")

        pcm = b"".join(chunk.pcm for chunk in chunks)
        audio = _pcm_to_mono_float(pcm, first.channels)
        segments, _info = self._get_model().transcribe(  # type: ignore[attr-defined]
            audio,
            language=self._language,
            initial_prompt="Conversación breve en español con SIRAH.",
            beam_size=1,
        )
        result = tuple(segments)
        average_logprob = (
            sum(segment.avg_logprob for segment in result) / len(result)
            if result
            else float("-inf")
        )
        confidence = max(0.0, min(1.0, exp(average_logprob)))
        duration = len(pcm) / (first.sample_rate * first.channels * 2)
        return Transcript(
            "".join(segment.text for segment in result).strip(),
            first.observed_at,
            first.observed_at + duration,
            confidence,
        )

    def _get_model(self) -> object:
        with self._model_lock:
            if self._model is None:
                factory = self._model_factory or _faster_whisper_model
                self._model = factory(self._model_name)
            return self._model


def _pcm_to_mono_float(pcm: bytes, channels: int) -> object:
    """Produce the NumPy waveform format accepted by Faster-Whisper."""
    import numpy

    if len(pcm) % (channels * 2):
        raise ValueError("PCM must contain complete 16-bit samples")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    if channels == 1:
        return numpy.asarray(samples, dtype=numpy.float32) / 32768
    return numpy.asarray(
        [
            sum(samples[index : index + channels]) / (32768 * channels)
            for index in range(0, len(samples), channels)
        ],
        dtype=numpy.float32,
    )


def _faster_whisper_model(model_name: str) -> object:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('install audio support: pip install -e ".[audio]"') from exc
    cache = os.getenv("SIRAH_WHISPER_CACHE", os.path.expanduser("~/.cache/sirah/whisper"))
    return WhisperModel(
        model_name,
        device=os.getenv("SIRAH_WHISPER_DEVICE", "cpu"),
        compute_type=os.getenv("SIRAH_WHISPER_COMPUTE_TYPE", "int8"),
        download_root=cache,
    )
