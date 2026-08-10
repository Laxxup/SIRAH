from __future__ import annotations

import json

import pytest

from sirah.conversation.contracts import IntentRequest
from sirah.conversation.errors import InvalidModelResponse
from sirah.conversation.ollama import OllamaIntentProposer, parse_intent_response


async def test_ollama_prompt_requests_json_without_cloud_format_parameter():
    requests: list[dict[str, object]] = []

    async def post(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> bytes:
        requests.append(json.loads(body))
        return (
            b'{"message":{"content":"{\\"intent\\":\\"silent\\",'
            b'\\"speech\\":null,\\"emotion\\":\\"neutral\\",\\"action\\":\\"none\\"}"}}'
        )

    proposer = OllamaIntentProposer.from_environment(
        environ={
            "SIRAH_OLLAMA_HOST": "https://example.invalid",
            "SIRAH_OLLAMA_MODEL": "test-model",
            "SIRAH_OLLAMA_API_KEY": "test-key",
        },
        timeout_s=10.0,
        budget=1,
        post=post,
    )

    await proposer.propose(IntentRequest("speech_ended", "hola", 1.0))

    assert "format" not in requests[0]
    assert "JSON object" in requests[0]["messages"][0]["content"]  # type: ignore[index]


def test_ollama_rejects_malformed_json_before_creating_a_proposal():
    with pytest.raises(InvalidModelResponse, match="valid JSON"):
        parse_intent_response(b"not json")
