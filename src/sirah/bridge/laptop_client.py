"""LaptopClient — connects from laptop to EdgeServer on Pi 4B."""

from __future__ import annotations

import asyncio
import logging
import uuid
from time import monotonic

from sirah.bridge.protocol import EdgeMessage, MessageKind
from sirah.errors import BridgeConnectionError, BridgeTimeoutError

__all__ = ["LaptopClient"]

logger = logging.getLogger(__name__)


class LaptopClient:
    def __init__(
        self,
        edge_host: str = "raspberrypi.local",
        edge_port: int = 8765,
        timeout: float = 10.0,
    ) -> None:
        self._host = edge_host
        self._port = edge_port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
            self._connected = True
            logger.info("LaptopClient connected to %s:%d", self._host, self._port)
        except asyncio.TimeoutError:
            raise BridgeConnectionError(
                f"connection to {self._host}:{self._port} timed out"
            )
        except OSError as exc:
            raise BridgeConnectionError(f"cannot reach {self._host}:{self._port}: {exc}")

    async def disconnect(self) -> None:
        self._connected = False
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
        self._reader = None

    async def health(self) -> bool:
        if not self._connected:
            return False
        try:
            await self._send_heartbeat()
            return True
        except (BridgeConnectionError, BridgeTimeoutError):
            return False

    async def send_tts(self, text: str) -> None:
        msg = EdgeMessage(
            msg_id=str(uuid.uuid4())[:8],
            kind=MessageKind.TTS_CMD,
            payload={"text": text},
            timestamp=monotonic(),
        )
        await self._send(msg)

    async def send_frame(self, frame_data: bytes) -> None:
        msg = EdgeMessage(
            msg_id=str(uuid.uuid4())[:8],
            kind=MessageKind.FRAME,
            payload={"data": "base64-placeholder", "size": len(frame_data)},
            timestamp=monotonic(),
        )
        await self._send(msg)

    async def _send_heartbeat(self) -> None:
        msg = EdgeMessage(
            msg_id=str(uuid.uuid4())[:8],
            kind=MessageKind.HEARTBEAT,
            timestamp=monotonic(),
        )
        await self._send(msg)
        try:
            response = await asyncio.wait_for(
                self._reader.readline() if self._reader else asyncio.sleep(0, result=b""),  # type: ignore[union-attr]
                timeout=2.0,
            )
            if not response:
                raise BridgeTimeoutError("no heartbeat response")
        except asyncio.TimeoutError:
            raise BridgeTimeoutError("heartbeat timeout")

    async def _send(self, msg: EdgeMessage) -> None:
        if self._writer is None:
            raise BridgeConnectionError("not connected")
        payload = msg.to_json() + "\n"
        try:
            self._writer.write(payload.encode())
            await asyncio.wait_for(self._writer.drain(), timeout=self._timeout)
        except (asyncio.TimeoutError, OSError) as exc:
            raise BridgeTimeoutError(f"send failed: {exc}")
