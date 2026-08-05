"""MQTTBridge — optional MQTT communication for multi-ESP32 setups."""

from __future__ import annotations

import asyncio
import json
import logging

__all__ = ["MQTTBridge"]

logger = logging.getLogger(__name__)


class MQTTBridge:
    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "sirah",
    ) -> None:
        self._broker = broker
        self._port = port
        self._topic_prefix = topic_prefix
        self._client: object | None = None
        self._connected = False

    @property
    def topic_command(self) -> str:
        return f"{self._topic_prefix}/command"

    @property
    def topic_telemetry(self) -> str:
        return f"{self._topic_prefix}/telemetry"

    async def connect(self) -> None:
        logger.info(
            "MQTTBridge would connect to %s:%d (requires paho-mqtt)",
            self._broker,
            self._port,
        )
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def publish_command(self, servo_id: int, angle: float) -> None:
        if not self._connected:
            return
        payload = json.dumps({"cmd": "servo", "id": servo_id, "angle": angle})
        logger.info("MQTT publish to %s: %s", self.topic_command, payload)

    @property
    def is_connected(self) -> bool:
        return self._connected
