"""Kokoro HTTP TTS adapter — synthesize speech via a remote Kokoro server."""

from __future__ import annotations

import json  # noqa: F401
import logging
import os
import tempfile
import uuid
from contextlib import suppress
from pathlib import Path
from time import monotonic

from sirah.errors import (
    SpeechBusyError,
    SpeechError,
    SpeechUnavailableError,
    TTSInvalidAudioError,
    TTSTimeoutError,
)
from sirah.types import SpeechCompletion

__all__ = ["KokoroHTTPTTS"]

logger = logging.getLogger(__name__)

_WAV_MAGIC = b"RIFF"


class KokoroHTTPTTS:
    """Synthesize speech by POSTing text to a Kokoro HTTP server.

    Audio is returned as WAV bytes, written to a temporary file, and played
    through the configured AudioPlayer (the same playback path as Piper).
    """

    def __init__(
        self,
        *,
        base_url: str,
        player,
        model: str = "kokoro",
        voice: str = "ef_dora",
        speed: float = 1.0,
        timeout: float = 30.0,
        temp_dir: Path | None = None,
        on_failure=None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._player = player
        self._model = model
        self._voice = voice
        self._speed = speed
        self._timeout = timeout
        self._temp_dir = temp_dir
        self._on_failure = on_failure
        self._busy = False
        self._failed = False

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def model(self) -> str:
        return self._model

    async def start(self) -> None:
        pass

    async def health(self) -> bool:
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=5)
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(f"{self._base_url}/audio/speech") as resp,
            ):
                return resp.status in (200, 405, 404)
        except Exception:
            return False

    async def speak(self, text: str) -> SpeechCompletion:
        if self._busy:
            raise SpeechBusyError("Kokoro is busy")
        if self._failed:
            raise SpeechUnavailableError("Kokoro is in a failed state")

        self._busy = True
        wav_path: Path | None = None
        started = monotonic()
        try:
            raw = await self._synthesize(text)
            wav_path = await self._write_wav(raw)
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
            raise SpeechError(f"Kokoro synthesis failed: {error}") from error
        finally:
            self._busy = False
            if wav_path is not None:
                with suppress(OSError):
                    wav_path.unlink()

    async def stop(self) -> None:
        self._busy = False

    def _mark_failed(self) -> None:
        if self._failed:
            return
        self._failed = True
        if self._on_failure is not None:
            self._on_failure()

    async def _synthesize(self, text: str) -> bytes:
        import aiohttp

        payload = {
            "model": self._model,
            "input": text,
            "voice": self._voice,
            "speed": self._speed,
            "response_format": "wav",
        }

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(f"{self._base_url}/audio/speech", json=payload) as resp,
            ):
                if resp.status == 429:
                    raise SpeechUnavailableError("Kokoro rate limited")
                if resp.status >= 500:
                    raise SpeechUnavailableError(f"Kokoro server error {resp.status}")
                if resp.status != 200:
                    raise SpeechUnavailableError(f"Kokoro HTTP {resp.status}")

                content_type = resp.headers.get("content-type", "")
                raw = await resp.read()

        except TimeoutError as exc:
            raise TTSTimeoutError(
                f"Kokoro timed out after {self._timeout}s"
            ) from exc
        except aiohttp.ClientError as exc:
            raise SpeechUnavailableError(
                f"Kokoro connection error: {exc}"
            ) from exc
        except (ConnectionError, OSError) as exc:
            raise SpeechUnavailableError(
                f"Kokoro connection error: {exc}"
            ) from exc

        if not raw:
            raise TTSInvalidAudioError("Kokoro returned empty body")
        if raw[:1] == b"{":
            raise TTSInvalidAudioError(
                f"Kokoro returned JSON instead of WAV: {raw[:200]!r}"
            )
        if "audio" not in content_type and "wav" not in content_type:
            raise TTSInvalidAudioError(
                f"Kokoro returned unexpected content-type: {content_type!r}"
            )
        if raw[:4] == _WAV_MAGIC:
            return raw
        raise TTSInvalidAudioError(
            f"Kokoro returned data without WAV header: {raw[:20]!r}"
        )

    async def _write_wav(self, raw: bytes) -> Path:
        try:
            fd, path = tempfile.mkstemp(suffix=".wav", dir=self._temp_dir)
            os.close(fd)
            Path(path).write_bytes(raw)
            return Path(path)
        except OSError as exc:
            raise TTSInvalidAudioError(f"cannot write Kokoro WAV: {exc}") from exc
