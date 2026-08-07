"""Deterministic diagnostics for runtime-owned microphone capture."""

from __future__ import annotations

import io
import os
import struct
import subprocess
import wave
from collections.abc import Callable

import pytest

from sirah.errors import AudioCaptureError, AudioFormatError
from sirah.voice.diagnostics import (
    AudioStage,
    analyze_pcm,
    capture_stage,
    validate_wav,
)
from sirah.voice.mic_capture import (
    CHANNELS,
    CHUNK_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    MicCapture,
)


def _wav(
    pcm: bytes,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    sample_width: int = SAMPLE_WIDTH,
) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setframerate(sample_rate)
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.writeframes(pcm)
    return buffer.getvalue()


def _clock(values: tuple[float, ...]) -> Callable[[], float]:
    timestamps = iter(values)
    final = values[-1]

    def now() -> float:
        return next(timestamps, final)

    return now


def test_validate_wav_reports_only_pcm_metrics() -> None:
    metrics = validate_wav(_wav(b"\x00\x00\xb8\x0b\x60\xf0"))

    assert metrics.bytes_count == 6
    assert metrics.duration_ms == 0
    assert metrics.sample_rate == 16_000
    assert metrics.channels == 1
    assert metrics.sample_width == 2
    assert metrics.rms == 2_886
    assert metrics.peak == 4_000
    assert metrics.is_silent is False
    assert not hasattr(metrics, "pcm")


def test_validate_wav_rejects_a_non_runtime_pcm_format() -> None:
    with pytest.raises(AudioFormatError, match="sample rate"):
        validate_wav(_wav(b"\x00\x00", sample_rate=8_000))


def test_validate_wav_rejects_a_truncated_declared_data_chunk() -> None:
    wav_data = bytearray(_wav(b"\x00\x00"))
    struct.pack_into("<I", wav_data, 40, 4)

    with pytest.raises(AudioFormatError, match="truncated WAV data"):
        validate_wav(bytes(wav_data))


def test_analyze_pcm_classifies_silence() -> None:
    metrics = analyze_pcm(b"\x00\x00" * 4)

    assert metrics.rms == 0
    assert metrics.peak == 0
    assert metrics.is_silent is True
    assert capture_stage(metrics) is AudioStage.SILENCE


def test_analyze_pcm_classifies_low_signal() -> None:
    metrics = analyze_pcm(b"\x64\x00" * 4)

    assert metrics.rms == 100
    assert metrics.peak == 100
    assert metrics.is_silent is False
    assert capture_stage(metrics) is AudioStage.SIGNAL_LOW


def test_analyze_pcm_rejects_an_odd_byte_count() -> None:
    with pytest.raises(AudioFormatError, match="odd byte count"):
        analyze_pcm(b"\x00")


@pytest.mark.asyncio
async def test_capture_start_rejects_an_exited_arecord_with_bounded_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = b"device busy: " + b"x" * 2_048

    class ExitedArecord:
        def __init__(self) -> None:
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO(stderr)

        def poll(self) -> int:
            return 1

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedArecord())

    capture = MicCapture("runtime-capture")
    with pytest.raises(AudioCaptureError, match="device busy") as error:
        await capture.start()

    assert len(str(error.value)) <= 512
    assert await capture.health() is False


@pytest.mark.asyncio
async def test_capture_start_wraps_process_start_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_arecord(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("arecord unavailable")

    monkeypatch.setattr(subprocess, "Popen", missing_arecord)

    with pytest.raises(AudioCaptureError, match="arecord could not start"):
        await MicCapture("runtime-capture").start()


@pytest.mark.asyncio
async def test_capture_start_detects_a_child_that_exits_after_the_first_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExitsAfterStartupYield:
        stdout = io.BytesIO()
        stderr = io.BytesIO(b"capture device closed")

        def __init__(self) -> None:
            self._poll_results = iter((None, 1))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: ExitsAfterStartupYield()
    )

    with pytest.raises(AudioCaptureError, match="capture device closed"):
        await MicCapture("runtime-capture").start()


@pytest.mark.asyncio
async def test_record_raises_when_the_child_exits_during_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExitsDuringCapture:
        stdout = io.BytesIO()
        stderr = io.BytesIO(b"capture disconnected")

        def __init__(self) -> None:
            self._poll_results = iter((None, None, None, 1))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 1

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: ExitsDuringCapture()
    )
    capture = MicCapture("runtime-capture")
    await capture.start()

    async def no_audio(timeout: float = 1.0) -> None:
        return None

    monkeypatch.setattr("sirah.voice.mic_capture.monotonic", _clock((0.0, 0.0, 1.0)))
    monkeypatch.setattr(capture, "read_chunk", no_audio)

    with pytest.raises(AudioCaptureError, match="capture disconnected"):
        await capture.record(duration_s=0.5)


@pytest.mark.asyncio
async def test_record_accepts_clean_exit_at_configured_capture_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FiniteArecord:
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def __init__(self) -> None:
            self._poll_results = iter((None, None, None, 0))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FiniteArecord())
    monkeypatch.setattr(
        "sirah.voice.mic_capture.monotonic", _clock((0.0, 0.0, 0.0, 1.0, 1.0))
    )

    capture = MicCapture("runtime-capture", duration=1.0)
    await capture.start()

    async def no_audio(timeout: float = 1.0) -> None:
        return None

    monkeypatch.setattr(capture, "read_chunk", no_audio)
    _, metrics = await capture.record(duration_s=2.0)

    assert metrics.is_silent is True


@pytest.mark.asyncio
async def test_record_rejects_clean_exit_before_configured_capture_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EarlyFiniteArecord:
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def __init__(self) -> None:
            self._poll_results = iter((None, None, 0))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: EarlyFiniteArecord()
    )
    monkeypatch.setattr(
        "sirah.voice.mic_capture.monotonic", _clock((0.0, 0.0, 0.0, 0.0))
    )

    capture = MicCapture("runtime-capture", duration=1.0)
    await capture.start()

    async def no_audio(timeout: float = 1.0) -> None:
        return None

    monkeypatch.setattr(capture, "read_chunk", no_audio)

    with pytest.raises(AudioCaptureError, match="before configured duration"):
        await capture.record(duration_s=2.0)


@pytest.mark.asyncio
async def test_record_rejects_early_clean_exit_even_when_poll_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = {"now": 0.0}

    class EarlyFiniteArecord:
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def __init__(self) -> None:
            self._poll_results = iter((None, None, 0))

        def poll(self) -> int | None:
            result = next(self._poll_results)
            if result == 0:
                clock["now"] = 1.0
            return result

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(
        subprocess, "Popen", lambda *args, **kwargs: EarlyFiniteArecord()
    )
    monkeypatch.setattr("sirah.voice.mic_capture.monotonic", lambda: clock["now"])

    capture = MicCapture("runtime-capture", duration=1.0)
    await capture.start()

    async def delayed_poll(timeout: float = 1.0) -> None:
        return None

    monkeypatch.setattr(capture, "read_chunk", delayed_poll)

    with pytest.raises(AudioCaptureError, match="before configured duration"):
        await capture.record(duration_s=2.0)


@pytest.mark.asyncio
async def test_record_drains_final_stdout_before_clean_finite_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"\x01\x00")
    os.close(write_fd)

    class FiniteArecord:
        def __init__(self) -> None:
            self.stdout = os.fdopen(read_fd, "rb", buffering=0)
            self.stderr = io.BytesIO()
            self._poll_results = iter((None, None, 0))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FiniteArecord())
    monkeypatch.setattr(
        "sirah.voice.mic_capture.monotonic", _clock((0.0, 0.0, 0.0, 1.0))
    )

    capture = MicCapture("runtime-capture", duration=1.0)
    await capture.start()
    _, metrics = await capture.record(duration_s=2.0)

    assert metrics.bytes_count == 2
    assert metrics.peak == 1


@pytest.mark.asyncio
async def test_record_drains_all_final_stdout_before_clean_finite_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"\x01\x00" * CHUNK_BYTES)
    os.close(write_fd)

    class FiniteArecord:
        def __init__(self) -> None:
            self.stdout = os.fdopen(read_fd, "rb", buffering=0)
            self.stderr = io.BytesIO()
            self._poll_results = iter((None, None, 0))

        def poll(self) -> int | None:
            return next(self._poll_results)

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FiniteArecord())
    monkeypatch.setattr(
        "sirah.voice.mic_capture.monotonic", _clock((0.0, 0.0, 0.0, 1.0))
    )

    capture = MicCapture("runtime-capture", duration=1.0)
    await capture.start()
    _, metrics = await capture.record(duration_s=2.0)

    assert metrics.bytes_count == CHUNK_BYTES * 2
    assert metrics.peak == 1
