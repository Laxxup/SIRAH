from __future__ import annotations

from dataclasses import dataclass

import pytest

from sirah.audio.contracts import AudioChunk
from sirah.audio.stt import FasterWhisperSTT


@dataclass
class FakeSegment:
    text: str
    avg_logprob: float


class FakeModel:
    def __init__(self) -> None:
        self.audio: object | None = None

    def transcribe(self, audio: object, **kwargs: object):
        self.audio = audio
        self.kwargs = kwargs
        return iter((FakeSegment("hola", -0.1), FakeSegment(" sirah", -0.1))), None


async def test_stt_lazily_transcribes_pcm_with_an_injected_model():
    models: list[FakeModel] = []

    def model_factory(_name: str) -> FakeModel:
        model = FakeModel()
        models.append(model)
        return model

    stt = FasterWhisperSTT("tiny", model_factory=model_factory)
    assert models == []

    transcript = await stt.transcribe((AudioChunk(b"\x00\x00\xff\x7f", 2, 1, 10.0),))

    assert transcript.text == "hola sirah"
    assert transcript.started_at == 10.0
    assert transcript.ended_at == 11.0
    assert transcript.confidence == pytest.approx(0.9048, rel=1e-4)
    assert models[0].audio.tolist() == [0.0, pytest.approx(32767 / 32768)]
    assert models[0].kwargs["language"] == "es"
    assert "español" in models[0].kwargs["initial_prompt"]
    assert models[0].kwargs["beam_size"] == 1


async def test_stt_preload_initializes_the_model_without_audio():
    models: list[FakeModel] = []

    def model_factory(_name: str) -> FakeModel:
        model = FakeModel()
        models.append(model)
        return model

    stt = FasterWhisperSTT("tiny", model_factory=model_factory)

    await stt.preload()

    assert len(models) == 1
    assert models[0].audio is None


async def test_stt_rejects_chunks_with_incompatible_audio_formats():
    stt = FasterWhisperSTT("tiny", model_factory=lambda _name: FakeModel())

    with pytest.raises(ValueError, match="sample rate and channels"):
        await stt.transcribe(
            (
                AudioChunk(b"\x00\x00", 16_000, 1, 1.0),
                AudioChunk(b"\x00\x00", 8_000, 1, 1.1),
            )
        )
