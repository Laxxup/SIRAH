"""Piper TTS — local text-to-speech via Python API."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from time import monotonic

from sirah.types import SpeechCompletion
from sirah.errors import SpeechBusyError, SpeechUnavailableError, SpeechError

__all__ = ["PiperTTS"]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path.home() / ".local" / "share" / "piper" / "voices"


class PiperTTS:
    def __init__(
        self,
        model_name: str = "es_ES-carlfm-x_low",
        model_dir: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._model_name = model_name
        self._model_dir = model_dir or str(DEFAULT_MODEL_PATH)
        self._timeout = timeout
        self._busy = False
        self._model_path = self._resolve_model_path()

    def _resolve_model_path(self) -> str:
        candidates = [
            Path(self._model_dir) / f"{self._model_name}.onnx",
            Path(self._model_dir) / self._model_name / f"{self._model_name}.onnx",
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        if not candidates[0].parent.exists():
            candidates[0].parent.mkdir(parents=True, exist_ok=True)
        return str(candidates[0])

    def _find_piper_bin(self) -> str:
        import sys

        candidates = [
            os.path.join(os.path.dirname(sys.executable), "piper"),
            os.path.join(os.path.dirname(sys.executable), "piper-tts"),
        ]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
        return "piper"

    async def health(self) -> bool:
        try:
            bin_path = self._find_piper_bin()
            proc = await asyncio.create_subprocess_exec(
                bin_path, "--help",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode in (0, 1)
        except FileNotFoundError:
            return False

    async def speak(self, text: str) -> SpeechCompletion:
        if self._busy:
            raise SpeechBusyError("Piper is busy")

        op_id = str(uuid.uuid4())[:8]
        self._busy = True
        t0 = monotonic()
        tmp_path = ""

        bin_path = self._find_piper_bin()

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            proc = await asyncio.create_subprocess_exec(
                bin_path,
                "--model", self._model_path,
                "--output_file", tmp_path,
                "--noise_scale", "0.667",
                "--length_scale", "1.0",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=text.encode("utf-8")),
                    timeout=self._timeout,
                )
                if proc.returncode != 0:
                    err_msg = stderr.decode()[:200] if stderr else "unknown"
                    raise SpeechError(f"Piper failed: {err_msg}")
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise SpeechError("Piper synthesis timed out")

            play_proc = await asyncio.create_subprocess_exec(
                "aplay", "-q", tmp_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(play_proc.wait(), timeout=self._timeout)
            except asyncio.TimeoutError:
                play_proc.kill()
                await play_proc.wait()

            duration = (monotonic() - t0) * 1000
            return SpeechCompletion(
                operation_id=op_id, success=True, duration_ms=duration
            )

        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError(f"Piper error: {exc}") from exc
        finally:
            self._busy = False
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def stop(self) -> None:
        self._busy = False
