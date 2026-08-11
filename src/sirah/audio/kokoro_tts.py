"""Local Apache-licensed Kokoro Spanish text-to-speech adapter."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Protocol


class _Pipeline(Protocol):
    def __call__(self, text: str, *, voice: str) -> Iterator[tuple[str, str, object]]: ...


_PipelineFactory = Callable[[], _Pipeline]


class KokoroTextToSpeech:
    """Lazy local Kokoro synthesis with an external Hugging Face cache."""

    sample_rate = 24_000

    def __init__(
        self,
        model: str,
        voice: str,
        cache: Path,
        pipeline_factory: _PipelineFactory | None = None,
    ) -> None:
        self._model = model
        self._voice = voice
        self._cache = cache
        self._pipeline_factory = pipeline_factory or self._load_pipeline
        self._pipeline: _Pipeline | None = None

    @classmethod
    def from_environment(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> KokoroTextToSpeech:
        values = os.environ if environ is None else environ
        return cls(
            values.get("SIRAH_LOCAL_TTS_MODEL", "hexgrad/Kokoro-82M"),
            values.get("SIRAH_LOCAL_TTS_VOICE", "ef_dora"),
            Path(values.get("SIRAH_LOCAL_TTS_CACHE", "~/.cache/sirah/kokoro")).expanduser(),
        )

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        return await asyncio.to_thread(self._synthesize, text)

    async def preload(self) -> None:
        """Load and warm the local model without retaining generated PCM."""
        await self.synthesize("Hola.")

    def _synthesize(self, text: str) -> bytes:
        pipeline = self._pipeline
        if pipeline is None:
            try:
                pipeline = self._pipeline_factory()
            except Exception as exc:
                raise RuntimeError(f"Kokoro model unavailable: {exc}") from exc
            self._pipeline = pipeline
        chunks = [audio for _graphemes, _phonemes, audio in pipeline(text, voice=self._voice) if audio is not None]
        return _float_audio_to_pcm(sample for chunk in chunks for sample in _samples(chunk))

    def _load_pipeline(self) -> _Pipeline:
        self._cache.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import snapshot_download
            from kokoro import KModel, KPipeline  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError('install local TTS support: pip install -e ".[local-tts]"') from exc
        snapshot = Path(
            snapshot_download(
                repo_id=self._model,
                cache_dir=str(self._cache),
                allow_patterns=["config.json", "kokoro-v1_0.pth", f"voices/{self._voice}.pt"],
            )
        )
        model = KModel(
            repo_id=self._model,
            config=str(snapshot / "config.json"),
            model=str(snapshot / "kokoro-v1_0.pth"),
        ).to("cpu").eval()
        return _CachedVoicePipeline(
            KPipeline(lang_code="e", repo_id=self._model, model=model),
            snapshot / "voices" / f"{self._voice}.pt",
        )


class _CachedVoicePipeline:
    def __init__(self, pipeline: _Pipeline, voice_path: Path) -> None:
        self._pipeline = pipeline
        self._voice_path = voice_path

    def __call__(self, text: str, *, voice: str) -> Iterator[tuple[str, str, object]]:
        return self._pipeline(text, voice=str(self._voice_path))


def _samples(audio: object) -> Iterable[float]:
    try:
        import numpy
    except ImportError as exc:
        raise RuntimeError('install local TTS support: pip install -e ".[local-tts]"') from exc
    return numpy.asarray(audio, dtype=numpy.float32).reshape(-1)


def _float_audio_to_pcm(samples: Iterable[float]) -> bytes:
    values = bytearray()
    for sample in samples:
        value = max(-32_768, min(32_767, int(float(sample) * 32_768)))
        values.extend(value.to_bytes(2, byteorder="little", signed=True))
    return bytes(values)
