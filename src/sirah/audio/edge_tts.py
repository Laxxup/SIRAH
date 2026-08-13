"""Microsoft Edge online TTS adapter that returns 24 kHz mono PCM."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

_Synthesize = Callable[[str, str], Awaitable[bytes]]
_Decode = Callable[[bytes], bytes]
_Stream = Callable[[str, str], AsyncIterator[bytes]]
_DecodeStream = Callable[[AsyncIterator[bytes]], AsyncIterator[bytes]]


class EdgeTextToSpeech:
    """Synthesize Spanish speech through edge-tts and decode it to PCM."""

    sample_rate = 24_000

    def __init__(
        self,
        voice: str,
        *,
        synthesize: _Synthesize | None = None,
        decode: _Decode | None = None,
        stream: _Stream | None = None,
        decode_stream: _DecodeStream | None = None,
    ) -> None:
        self._voice = voice
        self._synthesize = synthesize or _synthesize
        self._decode = decode or _decode_pcm
        self._stream = stream or _stream_encoded_audio
        self._decode_stream = decode_stream or _decode_pcm_stream

    @classmethod
    def from_environment(cls, *, environ: Mapping[str, str] | None = None) -> EdgeTextToSpeech:
        values = os.environ if environ is None else environ
        return cls(values.get("SIRAH_EDGE_TTS_VOICE", "es-MX-DaliaNeural"))

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        return self._decode(await self._synthesize(text, self._voice))

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield decoded PCM as Edge delivers the encoded audio response."""
        if text.strip():
            async for pcm in self._decode_stream(self._stream(text, self._voice)):
                if pcm:
                    yield pcm


async def _synthesize(text: str, voice: str) -> bytes:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError('install edge TTS support: pip install edge-tts') from exc

    chunks = []
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio" and isinstance(chunk.get("data"), bytes):
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def _stream_encoded_audio(text: str, voice: str) -> AsyncIterator[bytes]:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError('install edge TTS support: pip install edge-tts') from exc

    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio" and isinstance(chunk.get("data"), bytes):
            yield chunk["data"]


def _decode_pcm(mp3: bytes) -> bytes:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                "pipe:0",
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                "24000",
                "pipe:1",
            ],
            input=mp3,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for edge TTS playback") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("edge TTS audio decoding failed") from exc
    return result.stdout


async def _decode_pcm_stream(encoded: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Keep one ffmpeg process open so decoding begins before Edge completes."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-v",
            "error",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            "24000",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for edge TTS playback") from exc
    assert process.stdin is not None
    assert process.stdout is not None
    stdin = process.stdin
    stdout = process.stdout

    async def feed() -> None:
        try:
            async for chunk in encoded:
                stdin.write(chunk)
                await stdin.drain()
        finally:
            stdin.close()

    feeder = asyncio.create_task(feed())
    read: asyncio.Task[bytes] | None = None
    try:
        while True:
            if feeder.done():
                await feeder
            read = asyncio.create_task(stdout.read(4096))
            done, _ = await asyncio.wait({read, feeder}, return_when=asyncio.FIRST_COMPLETED)
            if feeder in done:
                await feeder
            pcm = await read
            read = None
            if not pcm:
                break
            yield pcm
        await feeder
        if await process.wait() != 0:
            raise RuntimeError("edge TTS audio decoding failed")
    finally:
        if read is not None and not read.done():
            read.cancel()
            try:
                await read
            except asyncio.CancelledError:
                pass
        if not feeder.done():
            feeder.cancel()
            try:
                await feeder
            except asyncio.CancelledError:
                pass
        if process.returncode is None:
            process.kill()
            await process.wait()
