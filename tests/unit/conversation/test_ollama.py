from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from sirah.conversation.contracts import IntentName, IntentRequest
from sirah.conversation.errors import (
    BudgetExhausted,
    ConfigurationError,
    ConversationTimeout,
    ProposalInFlight,
    RemoteError,
)
from sirah.conversation.ollama import OllamaIntentProposer, OllamaStreamProbe


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


def test_stream_probe_requires_key_for_loopback_lookalike_host():
    environment = {
        "SIRAH_OLLAMA_HOST": "http://localhost.attacker",
        "SIRAH_OLLAMA_MODEL": "test-model",
    }

    with pytest.raises(ConfigurationError, match="API_KEY"):
        OllamaStreamProbe.from_environment(environ=environment)


def test_ollama_client_requires_key_for_loopback_lookalike_host():
    environment = {
        "SIRAH_OLLAMA_HOST": "http://localhost.attacker",
        "SIRAH_OLLAMA_MODEL": "test-model",
    }

    with pytest.raises(ConfigurationError, match="API_KEY"):
        OllamaIntentProposer.from_environment(environ=environment)


async def test_ollama_client_sends_only_structured_request_and_parses_intent():
    calls: list[tuple[str, dict[str, str], bytes, float]] = []

    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        calls.append((url, headers, body, timeout))
        return b'{"message":{"content":"{\\"intent\\":\\"answer\\",\\"speech\\":\\"hola\\",\\"emotion\\":\\"friendly\\",\\"action\\":\\"none\\"}"}}'

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    proposal = await proposer.propose(IntentRequest("person_arrived", "hola", 1.0))

    assert proposal.intent is IntentName.ANSWER
    assert calls[0][0] == "https://example.invalid/api/chat"
    assert calls[0][1]["Authorization"] == "Bearer test-key"
    payload = json.loads(calls[0][2])
    assert payload["stream"] is False
    assert "format" not in payload
    assert "audio" not in json.dumps(payload)
    assert "frame" not in json.dumps(payload)
    assert "# Identidad y hechos verificados" in payload["messages"][0]["content"]
    assert "# Política de turno" in payload["messages"][0]["content"]
    assert "No hagas una pregunta" in payload["messages"][0]["content"]
    assert "solo cuando pregunten por colaborar" in payload["messages"][0]["content"]
    assert "anfitriona" in payload["messages"][0]["content"]
    assert "una frase breve" not in payload["messages"][0]["content"]
    assert "github.com/Laxxup/SIRAH" in payload["messages"][0]["content"]
    assert "sistema visual" in payload["messages"][0]["content"]


async def test_ollama_client_sends_configured_low_thinking_mode(monkeypatch):
    sent: list[dict[str, object]] = []

    async def post(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> bytes:
        sent.append(json.loads(body))
        return b'{"message":{"content":"{\\"intent\\":\\"silent\\",\\"speech\\":null,\\"emotion\\":\\"neutral\\",\\"action\\":\\"none\\"}"}}'

    monkeypatch.setenv("SIRAH_OLLAMA_THINK", "low")
    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )

    await proposer.propose(IntentRequest("latency_probe", "hola", 1.0))

    assert sent[0]["think"] == "low"


async def test_budget_prevents_a_second_cloud_proposal():
    async def post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
        return b'{"message":{"content":"{\\"intent\\":\\"silent\\",\\"speech\\":null,\\"emotion\\":\\"neutral\\",\\"action\\":\\"none\\"}"}}'

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
        return b'{"message":{"content":"{\\"intent\\":\\"silent\\",\\"speech\\":null,\\"emotion\\":\\"neutral\\",\\"action\\":\\"none\\"}"}}'

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


async def test_stream_probe_reports_first_content_without_retaining_response_text():
    async def stream(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> AsyncIterator[bytes]:
        yield b'{"message":{"thinking":"razonando","content":""},"done":false}\n'
        yield b'{"message":{"content":"Hola"},"done":false}\n'
        yield b'{"message":{"content":" mundo"},"done":true,"prompt_eval_count":123,"eval_count":4}\n'

    probe = OllamaStreamProbe.from_environment(environ=_environment(), stream=stream)

    metrics = await probe.measure("Prueba de latencia", context_limit=4, think=False)

    assert metrics.events == 3
    assert metrics.content_events == 2
    assert metrics.thinking_events == 1
    assert metrics.context_items == 4
    assert metrics.request_bytes > 0
    assert metrics.prompt_tokens == 123
    assert metrics.output_tokens == 4


async def test_stream_probe_sends_requested_thinking_mode_without_prompt_text_in_metrics():
    requests: list[dict[str, object]] = []

    async def stream(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> AsyncIterator[bytes]:
        requests.append(json.loads(body))
        yield b'{"message":{"content":"Hola"},"done":true}\n'

    probe = OllamaStreamProbe.from_environment(environ=_environment(), stream=stream)

    await probe.measure("Texto privado", think="low")

    assert requests[0]["think"] == "low"
