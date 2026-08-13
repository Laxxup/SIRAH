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


async def test_core_answers_how_are_you_without_claiming_human_feelings():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    response = await ConversationCore(proposer).respond(_transcript("¿Cómo estás?", confidence=0.6))

    assert response.speech == "Estoy disponible para ayudarte. ¿Qué necesitas?"
    assert proposer.requests == []


async def test_core_confirms_listening_at_reduced_confidence():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    response = await ConversationCore(proposer).respond(_transcript("Hola SIRAH, me escuchas", confidence=0.58))

    assert response.speech == "Sí, te escucho. ¿En qué puedo ayudarte?"
    assert proposer.requests == []


async def test_core_acknowledges_brief_confirmations_without_cloud():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    response = await ConversationCore(proposer).respond(_transcript("ah ok ok"))

    assert response.speech == "Me alegra. Si quieres, podemos seguir conversando o probar otra cosa."
    assert proposer.requests == []


async def test_core_handles_unverified_tec_activities_warmly_without_inventing():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    response = await ConversationCore(proposer).respond(
        _transcript("¿Hay taller de robótica en el Tec?")
    )

    assert "No tengo confirmación" in response.speech
    assert "facultad" in response.speech
    assert proposer.requests == []


async def test_core_describes_current_capabilities_and_development_goals_locally():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer)

    response = await core.respond(_transcript("¿Qué puedes hacer y qué te falta?"))

    assert "conversar" in response.speech
    assert "sistema visual" in response.speech
    assert "seguir rostros" in response.speech
    assert proposer.requests == []


async def test_core_introduces_its_open_source_project_locally():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer)

    response = await core.respond(_transcript("¿Te puedes presentar?"))

    assert "SIRAH" in response.speech
    assert "GitHub" in response.speech
    assert "github.com/Laxxup/SIRAH" in response.speech
    assert proposer.requests == []


async def test_core_shares_repository_when_someone_wants_to_try_or_contribute():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "ignored"))
    core = ConversationCore(proposer)

    response = await core.respond(_transcript("Quiero probarte y aportar ideas"))

    assert "github.com/Laxxup/SIRAH" in response.speech
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
