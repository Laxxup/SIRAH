"""Persistent Piper API synthesis with separately owned local playback."""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
import wave
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from time import monotonic
from typing import Protocol

from sirah.errors import SpeechBusyError, SpeechError, SpeechUnavailableError
from sirah.types import SpeechCompletion

__all__ = ["AplayPlayer", "PiperTTS"]


class PiperModel(Protocol):
    def synthesize_wav(self, text: str, output: wave.Wave_write) -> object: ...


class AudioPlayer(Protocol):
    async def play(self, wav_path: Path) -> bool: ...


class AplayPlayer:
    """Play a completed WAV only through the runtime-selected ALSA device."""

    def __init__(self, output_device: str, timeout_s: float = 10.0) -> None:
        self._output_device = output_device
        self._timeout_s = timeout_s

    async def play(self, wav_path: Path) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                "aplay",
                "-q",
                "-D",
                self._output_device,
                str(wav_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                return await asyncio.wait_for(process.wait(), timeout=self._timeout_s) == 0
            except TimeoutError:
                await _terminate_process(process)
                return False
            except asyncio.CancelledError:
                await _terminate_process(process)
                raise
        except OSError:
            return False


class PiperTTS:
    """Load an external Piper voice once and synthesize ephemeral WAV files."""

    def __init__(
        self,
        *,
        model_path: Path,
        config_path: Path,
        player: AudioPlayer,
        model_loader: Callable[[Path, Path], PiperModel] | None = None,
        temp_dir: Path | None = None,
        on_failure: Callable[[], None] | None = None,
    ) -> None:
        self._model_path = model_path
        self._config_path = config_path
        self._player = player
        self._model_loader = model_loader or _load_piper_model
        self._temp_dir = temp_dir
        self._model: PiperModel | None = None
        self._busy = False
        self._failed = False
        self._on_failure = on_failure

    async def start(self) -> None:
        if self._model is not None:
            return
        try:
            self._model = await asyncio.to_thread(
                self._model_loader, self._model_path, self._config_path
            )
        except Exception as error:
            self._mark_failed()
            raise SpeechUnavailableError("Piper model unavailable") from error

    async def health(self) -> bool:
        return self._model is not None and not self._failed

    async def speak(self, text: str) -> SpeechCompletion:
        if self._busy:
            raise SpeechBusyError("Piper is busy")
        if self._model is None or self._failed:
            raise SpeechUnavailableError("Piper model unavailable")

        self._busy = True
        wav_path: Path | None = None
        started = monotonic()
        try:
            descriptor, raw_path = tempfile.mkstemp(
                suffix=".wav", dir=self._temp_dir
            )
            os.close(descriptor)
            wav_path = Path(raw_path)
            await asyncio.to_thread(_synthesize, self._model, text, wav_path)
            played = await self._player.play(wav_path)
            if not played:
                self._mark_failed()
            return SpeechCompletion(
                operation_id=str(uuid.uuid4())[:8],
                success=played,
                duration_ms=(monotonic() - started) * 1000,
            )
        except SpeechError:
            raise
        except Exception as error:
            self._mark_failed()
            raise SpeechError("Piper synthesis failed") from error
        finally:
            self._busy = False
            if wav_path is not None:
                with suppress(OSError):
                    wav_path.unlink()

    async def stop(self) -> None:
        self._model = None
        self._busy = False

    def _mark_failed(self) -> None:
        if self._failed:
            return
        self._failed = True
        if self._on_failure is not None:
            self._on_failure()


def _load_piper_model(model_path: Path, config_path: Path) -> PiperModel:
    try:
        from piper.voice import PiperVoice
    except ImportError as error:
        raise SpeechUnavailableError("piper-tts is not installed") from error
    return PiperVoice.load(str(model_path), config_path=str(config_path))


def _synthesize(model: PiperModel, text: str, wav_path: Path) -> None:
    with wave.open(str(wav_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22_050)
        model.synthesize_wav(text, output)


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=1.0)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
