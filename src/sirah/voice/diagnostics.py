"""Derived, non-persistent audio diagnostics for one capture turn."""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from enum import StrEnum

from sirah.errors import AudioFormatError

__all__ = [
    "AudioMetrics",
    "CapturedAudio",
    "AudioStage",
    "analyze_pcm",
    "capture_stage",
    "validate_wav",
]

SILENT_RMS = 0
LOW_SIGNAL_RMS = 500


class AudioStage(StrEnum):
    """Sanitized terminal state for a server-side audio turn."""

    CAPTURE_FAILED = "capture_failed"
    SILENCE = "silence"
    SIGNAL_LOW = "signal_low"
    STT_EMPTY = "stt_empty"
    STT_FAILED = "stt_failed"
    STT_TIMEOUT = "stt_timeout"
    INTELLIGENCE_FAILED = "intelligence_failed"
    TTS_FAILED = "tts_failed"
    PLAYBACK_FAILED = "playback_failed"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class AudioMetrics:
    """Measurements that do not retain a turn's PCM payload."""

    bytes_count: int
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    rms: int
    peak: int
    is_silent: bool


@dataclass(frozen=True, slots=True)
class CapturedAudio:
    """One validated capture and its non-persistent derived measurements."""

    data: bytes
    sample_rate: int
    channels: int
    sample_width: int
    duration_ms: int
    metrics: AudioMetrics

    def __iter__(self):
        """Preserve the pre-Task-4 unpacking contract outside the runtime."""
        yield self.data
        yield self.metrics


def analyze_pcm(
    pcm: bytes,
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
    sample_width: int = 2,
) -> AudioMetrics:
    """Measure S16_LE PCM without keeping the supplied PCM."""
    _validate_format(sample_rate, channels, sample_width)
    if len(pcm) % sample_width:
        raise AudioFormatError("PCM has an odd byte count")

    samples = struct.iter_unpack("<h", pcm)
    sum_squares = 0
    peak = 0
    count = 0
    for (sample,) in samples:
        magnitude = abs(sample)
        sum_squares += sample * sample
        peak = max(peak, magnitude)
        count += 1
    rms = math.isqrt(sum_squares // count) if count else 0
    return AudioMetrics(
        bytes_count=len(pcm),
        duration_ms=(len(pcm) * 1_000) // (sample_rate * channels * sample_width),
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        rms=rms,
        peak=peak,
        is_silent=rms <= SILENT_RMS,
    )


def validate_wav(wav_data: bytes) -> AudioMetrics:
    """Validate the runtime WAV format and return derived metrics only."""
    try:
        with wave.open(io.BytesIO(wav_data), "rb") as reader:
            sample_rate = reader.getframerate()
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            _validate_format(sample_rate, channels, sample_width)
            pcm = reader.readframes(reader.getnframes())
            expected_bytes = reader.getnframes() * channels * sample_width
            if len(pcm) != expected_bytes:
                raise AudioFormatError("truncated WAV data")
    except (EOFError, wave.Error) as error:
        raise AudioFormatError("invalid WAV data") from error
    return analyze_pcm(
        pcm,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )


def capture_stage(metrics: AudioMetrics) -> AudioStage | None:
    """Classify a successful capture before it reaches STT."""
    if metrics.is_silent:
        return AudioStage.SILENCE
    if metrics.rms < LOW_SIGNAL_RMS:
        return AudioStage.SIGNAL_LOW
    return None


def _validate_format(sample_rate: int, channels: int, sample_width: int) -> None:
    if sample_rate != 16_000:
        raise AudioFormatError("WAV sample rate must be 16000 Hz")
    if channels != 1:
        raise AudioFormatError("WAV must have one channel")
    if sample_width != 2:
        raise AudioFormatError("WAV sample width must be 2 bytes")
