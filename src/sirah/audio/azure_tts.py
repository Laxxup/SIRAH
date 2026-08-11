"""Optional Azure Speech PCM adapter with no SDK dependency."""

from __future__ import annotations

import asyncio
import os
import urllib.request
from collections.abc import Awaitable, Callable, Mapping

from sirah.conversation.errors import ConfigurationError

HttpPost = Callable[[str, dict[str, str], bytes], Awaitable[bytes]]


class AzureTextToSpeech:
    def __init__(self, region: str, key: str, voice: str, post: HttpPost) -> None:
        self._region = region
        self._key = key
        self._voice = voice
        self._post = post

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        post: HttpPost | None = None,
    ) -> AzureTextToSpeech:
        values = os.environ if environ is None else environ
        key = values.get("SIRAH_AZURE_SPEECH_KEY")
        region = values.get("SIRAH_AZURE_SPEECH_REGION")
        if not key or not region:
            raise ConfigurationError("SIRAH_AZURE_SPEECH_KEY and REGION are required")
        return cls(region, key, values.get("SIRAH_AZURE_TTS_VOICE", "es-MX-DaliaNeural"), post or _post)

    async def synthesize(self, text: str) -> bytes:
        body = (
            f'<speak version="1.0" xml:lang="es-MX"><voice name="{self._voice}">'
            f"{_escape(text)}</voice></speak>"
        ).encode()
        return await self._post(
            f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1",
            {"Ocp-Apim-Subscription-Key": self._key, "Content-Type": "application/ssml+xml", "X-Microsoft-OutputFormat": "raw-16khz-16bit-mono-pcm"},
            body,
        )


class AzureOperationTextToSpeech:
    """Adapt Azure synthesis to the operation-aware conversation boundary."""

    def __init__(self, tts: AzureTextToSpeech) -> None:
        self._tts = tts
        self._cancelled: set[str] = set()

    async def synthesize(self, operation_id: str, text: str) -> bytes:
        pcm = await self._tts.synthesize(text)
        return b"" if operation_id in self._cancelled else pcm

    async def cancel(self, operation_id: str) -> None:
        self._cancelled.add(operation_id)


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _post(url: str, headers: dict[str, str], body: bytes) -> bytes:
    def send() -> bytes:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()

    return await asyncio.to_thread(send)
