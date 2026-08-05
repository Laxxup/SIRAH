"""gTTS fallback TTS — Google TTS via network."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from time import monotonic

from sirah.types import SpeechCompletion
from sirah.errors import SpeechError

__all__ = ["GTTSTTS"]

logger = logging.getLogger(__name__)


class GTTSTTS:
    def __init__(
        self,
        lang: str = "es",
        tld: str = "es",
        timeout: float = 10.0,
    ) -> None:
        self._lang = lang
        self._tld = tld
        self._timeout = timeout
        self._busy = False

    async def health(self) -> bool:
        return True

    async def speak(self, text: str) -> SpeechCompletion:
        if self._busy:
            from sirah.errors import SpeechBusyError
            raise SpeechBusyError("gTTS is busy")

        op_id = str(uuid.uuid4())[:8]
        self._busy = True
        t0 = monotonic()

        try:
            loop = asyncio.get_running_loop()

            def _synth() -> str:
                from gtts import gTTS

                tts = gTTS(text=text, lang=self._lang, tld=self._tld)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tts.save(tmp.name)
                    return tmp.name

            mp3_path = await loop.run_in_executor(None, _synth)

            proc = await asyncio.create_subprocess_exec(
                "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=self._timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

            duration = (monotonic() - t0) * 1000
            return SpeechCompletion(
                operation_id=op_id, success=True, duration_ms=duration
            )
        except Exception as exc:
            raise SpeechError(f"gTTS error: {exc}") from exc
        finally:
            self._busy = False

    async def stop(self) -> None:
        self._busy = False
