"""Mic capture via subprocess — PCM capture using arecord."""

from __future__ import annotations

import asyncio
import logging
import os
import select
import subprocess
from time import monotonic

from sirah.errors import AudioCaptureError, SpeechInputError
from sirah.voice.diagnostics import CapturedAudio, analyze_pcm, validate_wav

__all__ = ["MicCapture"]

logger = logging.getLogger(__name__)

CHUNK_BYTES = 4096
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
MAX_STDERR_BYTES = 480
STARTUP_LIVENESS_CHECKS = 2


class MicCapture:
    def __init__(self, device: str = "default", duration: float | None = None) -> None:
        self._device = device
        self._duration = duration
        self._proc: subprocess.Popen[bytes] | None = None
        self._running = False
        self._stderr_reason = ""
        self._expected_completion_at: float | None = None

    async def start(self) -> None:
        args = [
            "arecord",
            "-D", self._device,
            "-f", "S16_LE",
            "-r", str(SAMPLE_RATE),
            "-c", str(CHANNELS),
            "-t", "raw",
        ]
        if self._duration is not None:
            args.extend(["-d", str(int(self._duration))])

        try:
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as error:
            raise AudioCaptureError("arecord could not start") from error
        if self._duration is not None:
            self._expected_completion_at = monotonic() + int(self._duration)
        for check in range(STARTUP_LIVENESS_CHECKS):
            self._raise_if_exited()
            if check + 1 < STARTUP_LIVENESS_CHECKS:
                await asyncio.sleep(0)
        self._running = True
        logger.info("MicCapture started on device=%s", self._device)

    async def stop(self) -> None:
        self._running = False
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            self._proc = None

    async def health(self) -> bool:
        return self._running and self._proc is not None

    async def read_chunk(self, timeout: float = 1.0) -> bytes | None:
        if self._proc is None or self._proc.stdout is None:
            return None

        loop = asyncio.get_running_loop()

        def _read() -> bytes | None:
            if self._proc is None or self._proc.stdout is None:
                return None
            readable, _, _ = select.select([self._proc.stdout], [], [], timeout)
            if not readable:
                return None
            try:
                return os.read(self._proc.stdout.fileno(), CHUNK_BYTES)
            except (OSError, ValueError):
                return None

        return await loop.run_in_executor(None, _read)

    async def record(self, duration_s: float = 5.0) -> CapturedAudio:
        if not self._running:
            raise SpeechInputError("mic not started")

        t0 = monotonic()
        chunks: list[bytes] = []

        while monotonic() - t0 < duration_s:
            chunk = await self.read_chunk(timeout=0.5)
            final_chunk = self._raise_if_exited()
            if chunk:
                chunks.append(chunk)
            if final_chunk:
                chunks.append(final_chunk)
            if self._proc is None:
                break

        final_chunk = self._raise_if_exited()
        if final_chunk:
            chunks.append(final_chunk)

        raw = b"".join(chunks)
        metrics = analyze_pcm(raw)
        wav_data = self._raw_to_wav(raw)
        return CapturedAudio(
            data=wav_data,
            sample_rate=metrics.sample_rate,
            channels=metrics.channels,
            sample_width=metrics.sample_width,
            duration_ms=metrics.duration_ms,
            metrics=metrics,
        )

    def _raw_to_wav(self, raw: bytes) -> bytes:
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw)
        wav_data = buf.getvalue()
        validate_wav(wav_data)
        return wav_data

    @staticmethod
    def _read_stderr_reason(proc: subprocess.Popen[bytes]) -> str:
        if proc.stderr is None:
            return ""
        try:
            reason = proc.stderr.read(MAX_STDERR_BYTES + 1)
        except OSError:
            return ""
        return reason[:MAX_STDERR_BYTES].decode("utf-8", errors="replace").strip()

    @staticmethod
    def _drain_stdout(proc: subprocess.Popen[bytes]) -> bytes:
        if proc.stdout is None:
            return b""
        chunks: list[bytes] = []
        try:
            while chunk := os.read(proc.stdout.fileno(), CHUNK_BYTES):
                chunks.append(chunk)
        except (OSError, ValueError):
            return b""
        return b"".join(chunks)

    def _raise_if_exited(self) -> bytes:
        if self._proc is None:
            return b""
        observed_at = monotonic()
        exit_code = self._proc.poll()
        if exit_code is None:
            return b""
        if (
            exit_code == 0
            and self._expected_completion_at is not None
            and observed_at >= self._expected_completion_at
        ):
            final_chunk = self._drain_stdout(self._proc)
            self._proc = None
            self._running = False
            return final_chunk
        self._stderr_reason = self._read_stderr_reason(self._proc)
        self._proc = None
        self._running = False
        if exit_code == 0 and self._expected_completion_at is not None:
            raise AudioCaptureError("arecord exited before configured duration")
        raise AudioCaptureError(
            f"arecord exited: {self._stderr_reason or 'no reason'}"
        )
