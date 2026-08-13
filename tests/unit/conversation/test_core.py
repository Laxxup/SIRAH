from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal
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


@pytest.mark.parametrize(
    ("text", "response"),
    [
        ("¿Cómo estás?", "Puedo conversar contigo."),
        ("Hola SIRAH, me escuchas", "Sí, te escucho."),
        ("ah ok ok", "Perfecto, puedo esperar."),
        ("¿Hay taller de robótica en el Tec?", "No tengo ese dato confirmado."),
        ("¿Te puedes presentar?", "Soy SIRAH, un proyecto del ITCM."),
        ("Quiero probarte y aportar ideas", "Puedes conocer el proyecto en GitHub."),
    ],
)
async def test_core_delegates_social_turns_to_the_proposer(text: str, response: str):
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, response, EmotionName.FRIENDLY))

    result = await ConversationCore(proposer).respond(_transcript(text, confidence=0.9))

    assert result.speech == response
    assert proposer.requests[0].text == text


async def test_core_describes_current_capabilities_and_development_goals_locally():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer)

    response = await core.respond(_transcript("¿Qué puedes hacer y qué te falta?"))

    assert "conversar" in response.speech
    assert "sistema visual" in response.speech
    assert "seguir rostros" in response.speech
    assert proposer.requests == []


async def test_core_retains_sirah_response_in_cloud_context():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "Sí, puedo conocerte."))
    core = ConversationCore(proposer)

    await core.respond(_transcript("Hola"))
    await core.respond(_transcript("¿Qué piensas de eso?"))

    assert proposer.requests[1].context == (
        "Persona: Hola",
        "SIRAH: Sí, puedo conocerte.",
    )


async def test_core_retains_six_complete_turns_for_cloud_follow_ups():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "Sí, sigamos con ese tema."))
    core = ConversationCore(proposer)

    for number in range(7):
        await core.respond(_transcript(f"Tema {number}"))

    assert proposer.requests[-1].context == (
        "Persona: Tema 0",
        "SIRAH: Sí, sigamos con ese tema.",
        "Persona: Tema 1",
        "SIRAH: Sí, sigamos con ese tema.",
        "Persona: Tema 2",
        "SIRAH: Sí, sigamos con ese tema.",
        "Persona: Tema 3",
        "SIRAH: Sí, sigamos con ese tema.",
        "Persona: Tema 4",
        "SIRAH: Sí, sigamos con ese tema.",
        "Persona: Tema 5",
        "SIRAH: Sí, sigamos con ese tema.",
    )


async def test_core_accepts_valid_spanish_listening_response_from_cloud():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "Sí, te escucho."))
    response = await ConversationCore(proposer).respond(_transcript("Háblame normalmente", confidence=0.8))

    assert response.speech == "Sí, te escucho."


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
