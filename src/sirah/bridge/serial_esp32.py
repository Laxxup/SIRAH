"""SerialESP32Bridge — serial communication to ESP32 (servo/body)."""

from __future__ import annotations

import asyncio
import json
import logging

__all__ = ["SerialESP32Bridge"]

logger = logging.getLogger(__name__)

DEFAULT_BAUDRATE = 115200


class SerialESP32Bridge:
    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = 2.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
            )
            self._connected = True
            logger.info("SerialESP32Bridge connected to %s", self._port)
        except Exception as exc:
            logger.error("SerialESP32Bridge connection failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        self._connected = False
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()

    async def send_command(self, servo_id: int, angle: float) -> None:
        if not self._connected or self._writer is None:
            return
        cmd = json.dumps({"cmd": "servo", "id": servo_id, "angle": angle}) + "\n"
        self._writer.write(cmd.encode())
        await self._writer.drain()

    @property
    def is_connected(self) -> bool:
        return self._connected
