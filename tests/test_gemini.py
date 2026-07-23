"""Pruebas sin red del adaptador Gemini."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai.errors import ClientError, ServerError

from sirah.context import PresentContext
from sirah.errors import (
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
    InvalidIntelligenceResponseError,
)
from sirah.gemini import DEFAULT_GEMINI_MODEL, GeminiIntelligenceAdapter
from sirah.intelligence import DecisionType, IntelligenceRequest


def request() -> IntelligenceRequest:
    return IntelligenceRequest(
        "detente",
        PresentContext("session"),
        (
            {
                "name": "robot.stop",
                "description": "Detener.",
                "parameters": {},
            },
        ),
    )


class ScriptedModels:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(text=outcome)


def client(*outcomes: object) -> tuple[object, ScriptedModels]:
    models = ScriptedModels(list(outcomes))
    return SimpleNamespace(models=models), models


def valid_json() -> str:
    return json.dumps(
        {
            "decision_type": "request_capability",
            "response_text": "Me detendré.",
            "capability": "robot.stop",
            "parameters": {},
            "reason_code": "user_request",
        }
    )


def test_structured_response_converts_to_domain() -> None:
    sdk_client, models = client(valid_json())
    result = GeminiIntelligenceAdapter(client=sdk_client).decide(request())
    assert result.decision.decision_type is DecisionType.REQUEST_CAPABILITY
    assert result.decision.capability == "robot.stop"
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert (
        config.response_json_schema["properties"]["capability"]["anyOf"][0]["enum"]
        == ["robot.stop"]
    )


@pytest.mark.parametrize("payload", ["", "not json", '{"unexpected": true}'])
def test_empty_or_invalid_response_is_rejected(payload: str) -> None:
    sdk_client, _ = client(payload)
    with pytest.raises(InvalidIntelligenceResponseError):
        GeminiIntelligenceAdapter(client=sdk_client).decide(request())


def test_timeout_retries_up_to_maximum() -> None:
    sdk_client, models = client(TimeoutError(), TimeoutError())
    with pytest.raises(IntelligenceTimeoutError):
        GeminiIntelligenceAdapter(
            client=sdk_client, max_retries=1, sleep=lambda _: None
        ).decide(request())
    assert len(models.calls) == 2


def test_rate_limit_is_mapped_and_retried() -> None:
    sdk_client, models = client(
        ClientError(429, {"message": "quota"}), valid_json()
    )
    adapter = GeminiIntelligenceAdapter(
        client=sdk_client, max_retries=1, sleep=lambda _: None
    )
    assert adapter.decide(request()).decision.capability == "robot.stop"
    assert len(models.calls) == 2


def test_rate_limit_after_retries_is_observable() -> None:
    sdk_client, _ = client(
        ClientError(429, {"message": "quota"}),
        ClientError(429, {"message": "quota"}),
    )
    adapter = GeminiIntelligenceAdapter(
        client=sdk_client, max_retries=1, sleep=lambda _: None
    )
    with pytest.raises(IntelligenceRateLimitError):
        adapter.decide(request())
    assert adapter.metrics.rate_limits == 1


def test_server_error_is_recoverable() -> None:
    sdk_client, models = client(
        ServerError(503, {"message": "down"}), valid_json()
    )
    adapter = GeminiIntelligenceAdapter(
        client=sdk_client, max_retries=1, sleep=lambda _: None
    )
    assert adapter.decide(request()).decision.response_text
    assert len(models.calls) == 2


def test_non_recoverable_error_is_not_retried() -> None:
    sdk_client, models = client(ClientError(400, {"message": "bad"}))
    with pytest.raises(IntelligenceUnavailableError):
        GeminiIntelligenceAdapter(
            client=sdk_client, max_retries=3, sleep=lambda _: None
        ).decide(request())
    assert len(models.calls) == 1


def test_model_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIRAH_GEMINI_MODEL", "configured-model")
    assert GeminiIntelligenceAdapter(client=object()).model == "configured-model"
    monkeypatch.delenv("SIRAH_GEMINI_MODEL")
    assert GeminiIntelligenceAdapter(client=object()).model == DEFAULT_GEMINI_MODEL


def test_key_precedence_and_secret_not_exposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "top-secret-primary")
    monkeypatch.setenv("GOOGLE_API_KEY", "top-secret-secondary")
    adapter = GeminiIntelligenceAdapter(client=object())
    assert "top-secret" not in repr(adapter)
    assert "top-secret" not in str(adapter)

