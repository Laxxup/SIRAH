from __future__ import annotations

from datetime import UTC, datetime

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import IntentName, IntentProposal
from sirah.conversation.core import ConversationCore
from sirah.conversation.fakes import FakeIntentProposer


async def test_core_suite_handles_identity_time_context_and_safe_fallbacks():
    proposer = FakeIntentProposer(IntentProposal(IntentName.ANSWER, "Tienes cinco manzanas."))
    core = ConversationCore(proposer, clock=lambda: datetime(2026, 8, 11, 22, 30, tzinfo=UTC))

    identity = await core.respond(Transcript("¿Cómo te llamas?", 0, 1, 0.9))
    hour = await core.respond(Transcript("¿Qué hora es?", 1, 2, 0.9))
    first = await core.respond(Transcript("Tengo tres manzanas.", 2, 3, 0.9))
    follow_up = await core.respond(Transcript("Si compro dos más, ¿cuántas tengo?", 3, 4, 0.9))
    unclear = await core.respond(Transcript("", 4, 5, 0.9))

    assert "SIRAH" in identity.speech
    assert "22:30" in hour.speech
    assert first.speech == "Tienes cinco manzanas."
    assert follow_up.speech == "Tienes cinco manzanas."
    assert proposer.requests[-1].context[-1] == "Tengo tres manzanas."
    assert unclear.intent is IntentName.CLARIFY
