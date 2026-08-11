from __future__ import annotations

from datetime import UTC, datetime

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import IntentName, IntentProposal
from sirah.conversation.core import ConversationCore
from sirah.conversation.fakes import FakeIntentProposer


def _transcript(text: str, confidence: float = 0.9) -> Transcript:
    return Transcript(text, 1.0, 2.0, confidence)


async def test_core_answers_identity_and_time_locally_without_ollama():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer, clock=lambda: datetime(2026, 8, 11, 22, 30, tzinfo=UTC))

    identity = await core.respond(_transcript("¿Cómo te llamas?"))
    hour = await core.respond(_transcript("Hola SIRAH, dime la hora"))

    assert "SIRAH" in identity.speech
    assert "22:30" in hour.speech
    assert proposer.requests == []


async def test_core_rejects_low_confidence_before_ollama():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer, minimum_confidence=0.6)

    response = await core.respond(_transcript("nombre raro", confidence=0.2))

    assert response.speech == "No entendí bien, ¿puedes repetirlo?"
    assert proposer.requests == []


async def test_core_accepts_clear_local_time_pattern_at_reduced_confidence():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer, clock=lambda: datetime(2026, 8, 11, 22, 30, tzinfo=UTC))

    response = await core.respond(_transcript("Y si puede decir la hora", confidence=0.51))

    assert response.speech == "Son las 22:30."
    assert proposer.requests == []


async def test_core_repairs_english_response_once_then_uses_spanish_fallback():
    class EnglishTwice(FakeIntentProposer):
        async def propose(self, request):
            self.requests.append(request)
            return IntentProposal(IntentName.ANSWER, "I am ChatGPT and I can help")

    proposer = EnglishTwice(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer)

    response = await core.respond(_transcript("Háblame normalmente"))

    assert response.speech == "No entendí bien, ¿puedes reformularlo?"
    assert len(proposer.requests) == 2
