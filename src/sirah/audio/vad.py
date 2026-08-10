"""Dependency-injected voice activity detection."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sirah.audio.contracts import AudioChunk

_Predictor = Callable[[AudioChunk], float]


class VoiceActivityDetector:
    """Classify chunks using an injected predictor and explicit threshold."""

    def __init__(self, predictor: _Predictor, *, threshold: float = 0.5) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        self._predictor = predictor
        self._threshold = threshold

    async def is_speech(self, chunk: AudioChunk) -> bool:
        score = await asyncio.to_thread(self._predictor, chunk)
        return score >= self._threshold
