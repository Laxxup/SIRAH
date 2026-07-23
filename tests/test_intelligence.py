"""Contrato y prompt de inteligencia."""

import pytest

from sirah.context import ConversationMessage, PresentContext
from sirah.errors import InvalidIntelligenceResponseError
from sirah.fake_intelligence import FakeIntelligenceAdapter
from sirah.intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
    build_system_prompt,
)


def decision(**overrides: object) -> IntelligenceDecision:
    values: dict[str, object] = {
        "decision_type": "respond_only",
        "response_text": "Hola.",
        "capability": None,
        "parameters": {},
        "reason_code": None,
    }
    values.update(overrides)
    return IntelligenceDecision.from_mapping(values)


@pytest.mark.parametrize(
    "decision_type",
    [DecisionType.RESPOND_ONLY, DecisionType.CLARIFY, DecisionType.REJECT],
)
def test_non_mechanical_decisions_are_coherent(
    decision_type: DecisionType,
) -> None:
    assert decision(decision_type=decision_type.value).capability is None


def test_request_capability_requires_capability() -> None:
    with pytest.raises(InvalidIntelligenceResponseError, match="exige"):
        decision(decision_type="request_capability")


def test_non_request_rejects_capability() -> None:
    with pytest.raises(InvalidIntelligenceResponseError, match="Solo"):
        decision(capability="robot.home")


def test_additional_fields_are_rejected() -> None:
    with pytest.raises(InvalidIntelligenceResponseError, match="adicionales"):
        decision(unexpected=True)


def test_empty_and_oversized_response_are_rejected() -> None:
    with pytest.raises(InvalidIntelligenceResponseError, match="obligatorio"):
        decision(response_text="")
    with pytest.raises(InvalidIntelligenceResponseError, match="límite"):
        decision(response_text="1234").validate(max_response_characters=3)


def test_structurally_invalid_response_is_rejected() -> None:
    with pytest.raises(InvalidIntelligenceResponseError, match="incompleta"):
        IntelligenceDecision.from_mapping({"response_text": "hola"})


def test_fake_records_requests() -> None:
    response = IntelligenceResponse(decision(), "fake", "scripted")
    fake = FakeIntelligenceAdapter([response])
    request = IntelligenceRequest("hola", PresentContext("s"), ())
    assert fake.decide(request) is response
    assert fake.requests == [request]


def test_prompt_contains_safe_limited_context_not_secret() -> None:
    context = PresentContext(
        session_id="s",
        messages=(ConversationMessage("user", "hola"),),
        safety_state="normal",
    )
    prompt = build_system_prompt(
        IntelligenceRequest(
            "detente",
            context,
            (
                {
                    "name": "robot.stop",
                    "description": "Detener.",
                    "parameters": {},
                },
            ),
        )
    )
    assert "robot.stop" in prompt
    assert "detente" in prompt
    assert "GEMINI_API_KEY" not in prompt
    assert "GPIO" in prompt

