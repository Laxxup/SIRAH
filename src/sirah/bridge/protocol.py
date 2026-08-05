"""Bridge protocol — JSON message types for laptop ↔ edge communication."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
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
            data = data.decode("utf-8")
        obj = json.loads(data)
        return cls(
            msg_id=obj["msg_id"],
            kind=MessageKind(obj["kind"]),
            payload=obj.get("payload", {}),
            timestamp=obj.get("timestamp", 0.0),
        )
