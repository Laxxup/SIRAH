from __future__ import annotations

import pytest

from sirah.conversation.contracts import IntentName, IntentProposal, IntentRequest
from sirah.conversation.errors import InvalidModelResponse
from sirah.conversation.ollama import parse_intent_response


def test_intent_request_contains_only_event_text_and_monotonic_time():
    request = IntentRequest(event="person_arrived", text="hola", observed_at=1.0)

    assert request.event == "person_arrived"
    assert request.text == "hola"
    with pytest.raises(TypeError, match="event"):
        IntentRequest({"frame": "raw"}, None, 1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="text"):
        IntentRequest("person_arrived", {"memory": "raw"}, 1.0)  # type: ignore[arg-type]


def test_structured_response_accepts_only_the_closed_schema():
    proposal = parse_intent_response(b'{"intent":"greet","speech":"hola"}')

    assert proposal == IntentProposal(IntentName.GREET, "hola")
    with pytest.raises(InvalidModelResponse):
        parse_intent_response(b'{"intent":"greet","speech":"hola","extra":1}')
    with pytest.raises(InvalidModelResponse):
        parse_intent_response(b'{"intent":"silent","speech":"hola"}')
    with pytest.raises(InvalidModelResponse):
        parse_intent_response(b'{"intent":"greet","intent":"silent","speech":null}')
    with pytest.raises(InvalidModelResponse):
        parse_intent_response(b"\xff")


def test_intent_proposal_rejects_untyped_values():
    with pytest.raises(TypeError, match="intent"):
        IntentProposal("greet", "hola")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="speech"):
        IntentProposal(IntentName.GREET, 1)  # type: ignore[arg-type]
