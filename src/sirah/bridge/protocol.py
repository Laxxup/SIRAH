"""Bridge protocol — JSON message types for laptop ↔ edge communication."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["EdgeMessage", "MessageKind"]


class MessageKind(Enum):
    FRAME = "frame"
    AUDIO_CHUNK = "audio_chunk"
    TTS_CMD = "tts_cmd"
    TTS_DONE = "tts_done"
    PERCEPTION_EVENT = "perception_event"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class EdgeMessage:
    msg_id: str
    kind: MessageKind
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def to_json(self) -> str:
        return json.dumps({
            "msg_id": self.msg_id,
            "kind": self.kind.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
        })

    @classmethod
    def from_json(cls, data: str | bytes) -> EdgeMessage:
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid edge message encoding") from exc
        try:
            obj = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid edge message JSON") from exc
        if not isinstance(obj, dict):
            raise ValueError("invalid edge message object")

        msg_id = obj.get("msg_id")
        kind_name = obj.get("kind")
        payload = obj.get("payload", {})
        timestamp = obj.get("timestamp", 0.0)
        if not isinstance(msg_id, str) or not msg_id.strip():
            raise ValueError("invalid edge message msg_id")
        if not isinstance(kind_name, str):
            raise ValueError("invalid edge message kind")
        if not isinstance(payload, dict):
            raise ValueError("invalid edge message payload")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(float(timestamp))
        ):
            raise ValueError("invalid edge message timestamp")
        try:
            kind = MessageKind(kind_name)
        except ValueError as exc:
            raise ValueError("invalid edge message kind") from exc

        return cls(
            msg_id=msg_id,
            kind=kind,
            payload=payload,
            timestamp=float(timestamp),
        )
