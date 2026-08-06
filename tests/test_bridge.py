"""Test bridge protocol."""

from __future__ import annotations

import pytest

from sirah.bridge.protocol import EdgeMessage, MessageKind


def test_edge_message_serialization() -> None:
    msg = EdgeMessage(
        msg_id="abc123",
        kind=MessageKind.HEARTBEAT,
        payload={"key": "value"},
        timestamp=1.5,
    )
    json_str = msg.to_json()
    assert "abc123" in json_str
    assert "heartbeat" in json_str
    assert "key" in json_str


def test_edge_message_deserialization() -> None:
    json_str = '{"msg_id":"abc","kind":"tts_cmd","payload":{"text":"hola"},"timestamp":2.0}'
    msg = EdgeMessage.from_json(json_str)
    assert msg.msg_id == "abc"
    assert msg.kind == MessageKind.TTS_CMD
    assert msg.payload["text"] == "hola"
    assert msg.timestamp == 2.0


def test_edge_message_from_bytes() -> None:
    data = b'{"msg_id":"xyz","kind":"heartbeat","payload":{},"timestamp":0.0}'
    msg = EdgeMessage.from_json(data)
    assert msg.msg_id == "xyz"
    assert msg.kind == MessageKind.HEARTBEAT


def test_message_kind_values() -> None:
    assert MessageKind.FRAME.value == "frame"
    assert MessageKind.AUDIO_CHUNK.value == "audio_chunk"
    assert MessageKind.TTS_CMD.value == "tts_cmd"
    assert MessageKind.HEARTBEAT.value == "heartbeat"
    assert MessageKind.ERROR.value == "error"


@pytest.mark.parametrize(
    "data",
    [
        "{}",
        '{"msg_id":"abc","kind":"unknown"}',
        '{"msg_id":"abc","kind":"heartbeat","payload":[]}',
        '{"msg_id":"abc","kind":"heartbeat","timestamp":"now"}',
        "not json",
    ],
)
def test_edge_message_rejects_malformed_input(data: str) -> None:
    with pytest.raises(ValueError, match="invalid edge message"):
        EdgeMessage.from_json(data)
