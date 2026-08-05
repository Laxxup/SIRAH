"""Edge Server — lightweight server running on Raspberry Pi 4B.

Handles:
- Webcam capture → sends frames to laptop
- Mic capture → sends audio chunks to laptop
- Receives TTS commands → plays via Piper
- Bridges Serial commands → ESP32
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from time import monotonic

from sirah.bridge.protocol import EdgeMessage, MessageKind

__all__ = ["EdgeServer"]

logger = logging.getLogger(__name__)


class EdgeServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        tts_cmd: str = "piper",
        speaker: str = "default",
    ) -> None:
        self._host = host
        self._port = port
        self._tts_cmd = tts_cmd
        self._speaker = speaker
        self._running = False
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        self._running = True
        logger.info("EdgeServer listening on %s:%d", self._host, self._port)

    async def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in self._clients:
            writer.close()
            await writer.wait_closed()
        self._clients.clear()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._clients.add(writer)
        addr = writer.get_extra_info("peername", ("unknown", 0))
        logger.info("Edge client connected: %s", addr)

        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    break

                msg = EdgeMessage.from_json(line)
                if msg.kind == MessageKind.TTS_CMD:
                    await self._handle_tts(msg)
                elif msg.kind == MessageKind.HEARTBEAT:
                    pong = EdgeMessage(
                        msg_id=str(uuid.uuid4())[:8],
                        kind=MessageKind.HEARTBEAT,
                        timestamp=monotonic(),
                    )
                    writer.write((pong.to_json() + "\n").encode())
                    await writer.drain()
                else:
                    logger.debug("Edge received: %s", msg.kind.value)
        except (ConnectionError, json.JSONDecodeError) as exc:
            logger.warning("Edge client error: %s", exc)
        finally:
            self._clients.discard(writer)
            writer.close()
            await writer.wait_closed()

    async def _handle_tts(self, msg: EdgeMessage) -> None:
        text = msg.payload.get("text", "")
        if not text:
            return

        logger.info("Edge TTS: %s...", text[:50])
        proc = await asyncio.create_subprocess_exec(
            self._tts_cmd,
            "--output-raw",
            "-s", self._speaker,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        stdout, _ = await proc.communicate(input=(text + "\n").encode())

        if stdout:
            play = await asyncio.create_subprocess_exec(
                "aplay", "-q",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await play.communicate(input=stdout)
            await play.wait()
