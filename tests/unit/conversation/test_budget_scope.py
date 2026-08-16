from __future__ import annotations

import json

import pytest

from sirah.audio.contracts import Transcript
from sirah.audio.fakes import FakeOperationTTS, FakePCMPlayer
from sirah.conversation.contracts import IntentName, IntentRequest
from sirah.conversation.core import ConversationCore
from sirah.conversation.errors import BudgetExhausted
from sirah.conversation.ollama import OllamaIntentProposer
from sirah.conversation.session import ConversationSession


def _environment() -> dict[str, str]:
    return {
        "SIRAH_OLLAMA_HOST": "https://example.invalid",
        "SIRAH_OLLAMA_MODEL": "test-model",
        "SIRAH_OLLAMA_API_KEY": "test-key",
    }


def _transcript(text: str) -> Transcript:
    return Transcript(text, 1.0, 2.0, 0.9)


def _cloud_response(speech: str | None, *, intent: str = "answer") -> bytes:
    return json.dumps(
        {
            "message": {
                "content": json.dumps(
                    {
                        "intent": intent,
                        "speech": speech,
                        "emotion": "neutral",
                        "action": "none",
                    }
                )
            }
        }
    ).encode()


async def test_conversation_session_runs_more_than_ten_cloud_turns():
    calls: list[bytes] = []

    async def post(_url: str, _headers: dict[str, str], body: bytes, _timeout: float) -> bytes:
        calls.append(body)
        return _cloud_response("Hola, sigamos.")

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    session = ConversationSession(proposer, FakeOperationTTS(), FakePCMPlayer())

    for turn in range(12):
        result = await session.respond(_transcript(f"turno {turn}"))

        assert result.proposal.speech == "Hola, sigamos."
    assert len(calls) == 12


async def test_proposer_caps_proposals_within_a_turn_until_renewed():
    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        return _cloud_response(None, intent="silent")

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=2, post=post
    )
    request = IntentRequest("person_arrived", None, 1.0)

    await proposer.propose(request)
    await proposer.propose(request)
    with pytest.raises(BudgetExhausted):
        await proposer.propose(request)

    proposer.start_turn()
    assert await proposer.propose(request) is not None


async def test_repair_path_is_bounded_to_the_turn_budget():
    calls: list[str] = []

    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        calls.append("cloud")
        return _cloud_response("I am ChatGPT and can help")

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=2, post=post
    )
    session = ConversationSession(
        proposer, FakeOperationTTS(), FakePCMPlayer(), core=ConversationCore(proposer)
    )

    result = await session.respond(_transcript("Háblame normalmente"))

    assert len(calls) == 2
    assert result.proposal.intent is IntentName.CLARIFY


async def test_budget_cap_halts_the_repair_attempt():
    calls: list[str] = []

    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        calls.append("cloud")
        return _cloud_response("I am ChatGPT and can help")

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    session = ConversationSession(
        proposer, FakeOperationTTS(), FakePCMPlayer(), core=ConversationCore(proposer)
    )

    result = await session.respond(_transcript("Háblame normalmente"))

    assert len(calls) == 1
    assert result.proposal.intent is IntentName.CLARIFY


async def test_exhausted_turn_does_not_poison_later_independent_turns():
    responses = ["I am ChatGPT and can help", "Hola, sigamos."]
    calls: list[str] = []

    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        calls.append("cloud")
        return _cloud_response(responses.pop(0))

    proposer = OllamaIntentProposer.from_environment(
        environ=_environment(), timeout_s=10.0, budget=1, post=post
    )
    session = ConversationSession(
        proposer, FakeOperationTTS(), FakePCMPlayer(), core=ConversationCore(proposer)
    )

    first = await session.respond(_transcript("Háblame normalmente"))
    second = await session.respond(_transcript("¿Cómo estás?"))

    assert first.proposal.intent is IntentName.CLARIFY
    assert second.proposal.speech == "Hola, sigamos."
    assert len(calls) == 2