from __future__ import annotations

from sirah.audio.contracts import AudioChunk
from sirah.audio.vad import SileroVoiceActivityDetector, VoiceActivityDetector


async def test_vad_classifies_predictor_scores_at_the_configured_threshold():
    seen: list[AudioChunk] = []

    def predictor(chunk: AudioChunk) -> float:
        seen.append(chunk)
        return 0.75

    chunk = AudioChunk(b"pcm", 16_000, 1, 1.0)
    detector = VoiceActivityDetector(predictor, threshold=0.75)

    assert await detector.is_speech(chunk) is True
    assert seen == [chunk]


async def test_vad_reports_silence_for_scores_below_the_threshold():
    detector = VoiceActivityDetector(lambda _chunk: 0.74, threshold=0.75)

    assert await detector.is_speech(AudioChunk(b"pcm", 16_000, 1, 1.0)) is False


async def test_silero_adapter_uses_injected_official_model_and_threshold():
    calls = []

    def model(samples, sample_rate):
        calls.append((samples, sample_rate))
        return 0.8

    detector = SileroVoiceActivityDetector(model, threshold=0.75, samples_factory=list)

    assert await detector.is_speech(AudioChunk(b"\x00\x00" * 512, 16_000, 1, 1.0)) is True
    assert calls[0][1] == 16_000


async def test_silero_adapter_resets_state_between_turns():
    class Model:
        def __call__(self, _samples, _rate):
            return 0.0

        def reset_states(self):
            self.reset = True

    model = Model()
    detector = SileroVoiceActivityDetector(model, samples_factory=list)

    await detector.reset()

    assert model.reset is True
