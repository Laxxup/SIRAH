"""Dependency-injected voice activity detection."""

from __future__ import annotations

import asyncio
from array import array
from collections.abc import Callable
from typing import Any, Protocol, cast

from sirah.audio.contracts import AudioChunk

_Predictor = Callable[[AudioChunk], float]


class _SileroModel(Protocol):
    def __call__(self, samples: object, sample_rate: int) -> object: ...


class VoiceActivityDetector:
    """Classify chunks using an injected predictor and explicit threshold."""

    def __init__(self, predictor: _Predictor, *, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self._predictor = predictor
        self._threshold = threshold

    async def is_speech(self, chunk: AudioChunk, *, threshold: float | None = None) -> bool:
        score = await asyncio.to_thread(self._predictor, chunk)
        return score >= (self._threshold if threshold is None else threshold)


class SileroVoiceActivityDetector:
    """Local adapter for the official `silero-vad` ONNX distribution."""

    def __init__(
        self,
        model: _SileroModel,
        *,
        threshold: float = 0.5,
        samples_factory: Callable[[array], object] | None = None,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self._model = model
        self._threshold = threshold
        self._samples_factory = samples_factory or _torch_samples

    @classmethod
    def from_official_distribution(cls, *, threshold: float = 0.5) -> SileroVoiceActivityDetector:
        try:
            from silero_vad import load_silero_vad  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError('install VAD support: pip install -e ".[vad]"') from exc
        return cls(load_silero_vad(onnx=True), threshold=threshold)

    async def is_speech(self, chunk: AudioChunk, *, threshold: float | None = None) -> bool:
        if chunk.sample_rate not in (8_000, 16_000) or chunk.channels != 1:
            raise ValueError("Silero VAD requires mono 8 kHz or 16 kHz PCM")
        return await asyncio.to_thread(self._classify, chunk, threshold)

    def _classify(self, chunk: AudioChunk, threshold: float | None) -> bool:
        samples = array("h")
        samples.frombytes(chunk.pcm)
        score = self._model(self._samples_factory(samples), chunk.sample_rate)
        return float(score if isinstance(score, (float, int)) else cast(Any, score)) >= (self._threshold if threshold is None else threshold)


def _torch_samples(samples: array) -> object:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError('install VAD support: pip install -e ".[vad]"') from exc
    return torch.tensor(samples, dtype=torch.float32) / 32768.0
