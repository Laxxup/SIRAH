from __future__ import annotations

from sirah.audio.contracts import AudioChunk
from sirah.audio.vad import VoiceActivityDetector


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
