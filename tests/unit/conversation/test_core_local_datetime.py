from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal
from sirah.conversation.core import ConversationCore
from sirah.conversation.fakes import FakeIntentProposer


def _transcript(text: str, confidence: float = 0.9) -> Transcript:
    return Transcript(text, 1.0, 2.0, confidence)


async def _core_with_clock() -> tuple[ConversationCore, FakeIntentProposer]:
    proposer = FakeIntentProposer(
        IntentProposal(
            IntentName.ANSWER, "Puedo ayudarte con eso.", EmotionName.FRIENDLY
        )
    )
    core = ConversationCore(
        proposer, clock=lambda: datetime(2026, 8, 11, 22, 30, tzinfo=UTC)
    )
    return core, proposer


@pytest.mark.parametrize(
    "text",
    [
        "Buen día",
        "vida diaria",
        "¿Y eso para qué sirve en la vida diaria?",
        "¿Cómo estuvo tu día?",
        "a esta hora",
        "una hora",
        "dentro de una hora",
        "¿A qué hora es la clase?",
        "¿En qué día es la reunión?",
        "¿Cuál es la fecha límite?",
    ],
)
async def test_date_time_false_positives_route_to_the_proposer(text: str):
    core, proposer = await _core_with_clock()

    result = await core.respond(_transcript(text))

    assert result.speech == "Puedo ayudarte con eso."
    assert proposer.requests[0].text == text


@pytest.mark.parametrize(
    "text",
    [
        "¿Qué día es?",
        "¿Qué día es hoy?",
        "¿Qué fecha es?",
        "¿Cuál es la fecha?",
        "¿Qué fecha es hoy?",
    ],
)
async def test_explicit_date_requests_stay_local(text: str):
    core, proposer = await _core_with_clock()

    result = await core.respond(_transcript(text))

    assert result.speech == "Hoy es 2026-08-11."
    assert proposer.requests == []


@pytest.mark.parametrize(
    "text",
    [
        "¿Qué hora es?",
        "¿Qué hora es ahora?",
        "dime la hora",
    ],
)
async def test_explicit_time_requests_stay_local(text: str):
    core, proposer = await _core_with_clock()

    result = await core.respond(_transcript(text))

    assert result.speech == "Son las 22:30."
    assert proposer.requests == []


async def test_follow_up_with_vida_diaria_reaches_proposer_with_context():
    proposer = FakeIntentProposer(
        IntentProposal(
            IntentName.ANSWER,
            "Sí, la inteligencia artificial tiene aplicaciones diarias.",
            EmotionName.FRIENDLY,
        )
    )
    core = ConversationCore(
        proposer, clock=lambda: datetime(2026, 8, 11, 22, 30, tzinfo=UTC)
    )

    await core.respond(_transcript("¿Qué es la inteligencia artificial?"))
    follow_up = await core.respond(
        _transcript("¿Y eso para qué sirve en la vida diaria?")
    )

    assert (
        follow_up.speech == "Sí, la inteligencia artificial tiene aplicaciones diarias."
    )
    assert proposer.requests[1].text == "¿Y eso para qué sirve en la vida diaria?"
    assert proposer.requests[1].context == (
        "Persona: ¿Qué es la inteligencia artificial?",
        "SIRAH: Sí, la inteligencia artificial tiene aplicaciones diarias.",
    )
