from __future__ import annotations

import asyncio
import json

import pytest

from sirah.conversation.contracts import IntentName, IntentRequest
from sirah.conversation.errors import (
    BudgetExhausted,
    ConfigurationError,
    ConversationTimeout,
    ProposalInFlight,
    RemoteError,
)
from sirah.conversation.ollama import OllamaIntentProposer


def _environment() -> dict[str, str]:
    return {
        "SIRAH_OLLAMA_HOST": "https://example.invalid",
        "SIRAH_OLLAMA_MODEL": "test-model",
        "SIRAH_OLLAMA_API_KEY": "test-key",
    }


def test_environment_configuration_requires_all_ollama_values():
    with pytest.raises(ConfigurationError):
        OllamaIntentProposer.from_environment(environ={})
    with pytest.raises(ValueError, match="between 10 and 20"):
        OllamaIntentProposer.from_environment(environ=_environment(), timeout_s=9.0)
    with pytest.raises(ConfigurationError, match="from_environment"):
        OllamaIntentProposer(
            "https://example.invalid",
            "test-model",
            "test-key",
            timeout_s=10.0,
            budget=1,
            post=lambda url, headers, body, timeout: asyncio.sleep(0),
        )


async def test_ollama_client_sends_only_structured_request_and_parses_intent():
    calls: list[tuple[str, dict[str, str], bytes, float]] = []

    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        calls.append((url, headers, body, timeout))
        return b'{"message":{"content":"{\\"intent\\":\\"greet\\",\\"speech\\":\\"hola\\"}"}}'

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    proposal = await proposer.propose(IntentRequest("person_arrived", "hola", 1.0))

    assert proposal.intent is IntentName.GREET
    assert calls[0][0] == "https://example.invalid/api/chat"
    assert calls[0][1]["Authorization"] == "Bearer test-key"
    payload = json.loads(calls[0][2])
    assert payload["stream"] is False
    assert "audio" not in json.dumps(payload)
    assert "frame" not in json.dumps(payload)


async def test_budget_prevents_a_second_cloud_proposal():
    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        return b'{"message":{"content":"{\\"intent\\":\\"silent\\",\\"speech\\":null}"}}'

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    request = IntentRequest("person_arrived", None, 1.0)
    await proposer.propose(request)

    with pytest.raises(BudgetExhausted):
        await proposer.propose(request)


async def test_cloud_timeout_and_remote_error_are_typed():
    async def timeout_post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        raise TimeoutError

    async def broken_post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        raise RuntimeError("unexpected response")

    request = IntentRequest("person_arrived", None, 1.0)
    timing_out = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, post=timeout_post
    )
    broken = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, post=broken_post
    )

    with pytest.raises(ConversationTimeout):
        await timing_out.propose(request)
    with pytest.raises(RemoteError):
        await broken.propose(request)


async def test_single_flight_rejects_a_concurrent_proposal():
    started = asyncio.Event()
    release = asyncio.Event()

    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        started.set()
        await release.wait()
        return b'{"message":{"content":"{\\"intent\\":\\"silent\\",\\"speech\\":null}"}}'

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=2, post=post
    )
    request = IntentRequest("person_arrived", None, 1.0)
    first = asyncio.create_task(proposer.propose(request))
    await started.wait()

    with pytest.raises(ProposalInFlight):
        await proposer.propose(request)
    release.set()
    await first
