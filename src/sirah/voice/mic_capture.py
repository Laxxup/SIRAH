"""Mic capture via subprocess — PCM capture using arecord."""

from __future__ import annotations

import asyncio
import logging
import os
import select
import subprocess
from time import monotonic

from sirah.errors import SpeechInputError

__all__ = ["MicCapture"]

logger = logging.getLogger(__name__)

CHUNK_BYTES = 4096
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2


class MicCapture:
    def __init__(self, device: str = "default", duration: float | None = None) -> None:
        self._device = device
        self._duration = duration
        self._proc: subprocess.Popen[bytes] | None = None
        self._running = False
        self._accumulated: list[bytes] = []

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

        self._proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
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

    async def record(self, duration_s: float = 5.0) -> bytes:
        if not self._running:
            raise SpeechInputError("mic not started")

        t0 = monotonic()
        chunks: list[bytes] = []

        while monotonic() - t0 < duration_s:
            chunk = await self.read_chunk(timeout=0.5)
            if chunk:
                chunks.append(chunk)

        raw = b"".join(chunks)

        return self._raw_to_wav(raw)

    def _raw_to_wav(self, raw: bytes) -> bytes:
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(raw)
        return buf.getvalue()
