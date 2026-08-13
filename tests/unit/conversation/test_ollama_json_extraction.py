from __future__ import annotations

import pytest

from sirah.conversation.errors import InvalidModelResponse
from sirah.conversation.ollama import _extract_json_object, parse_intent_response


def test_parse_extracts_json_from_prose() -> None:
    raw = "Claro, aquí tienes: {\"intent\":\"answer\",\"speech\":\"hola\",\"emotion\":\"friendly\",\"action\":\"none\"} fin.".encode()
    p = parse_intent_response(raw)
    assert p.intent.value == "answer"
    assert p.speech == "hola"


def test_parse_extracts_json_from_markdown_fence() -> None:
    raw = b'```json\n{"intent":"silent","speech":null,"emotion":"neutral","action":"none"}\n```'
    p = parse_intent_response(raw)
    assert p.intent.value == "silent"
    assert p.speech is None


def test_parse_still_accepts_plain_json() -> None:
    raw = b'{"intent":"answer","speech":"ok","emotion":"friendly","action":"none"}'
    assert parse_intent_response(raw).speech == "ok"


def test_parse_garbage_raises_invalid() -> None:
    with pytest.raises(InvalidModelResponse):
        parse_intent_response(b"no json here at all")


def test_extract_json_object_no_brace() -> None:
    with pytest.raises(InvalidModelResponse):
        _extract_json_object("nope")


def test_extract_json_object_handles_inner_braces_and_strings() -> None:
    text = 'x "{a:b}" {"intent":"answer","speech":"a } b","emotion":"friendly","action":"none"} y'
    assert _extract_json_object(text) == '{"intent":"answer","speech":"a } b","emotion":"friendly","action":"none"}'
