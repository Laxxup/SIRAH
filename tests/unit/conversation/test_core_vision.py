"""M8.1: the conversation core injects the current vision context per turn.

`ConversationCore` receives an optional `vision_context` provider. The
compact vision block must be part of the cloud request context (so the
LLM can ground answers on what SIRAH currently sees) but must NOT be
stored in the remembered turn memory: stale perception would then be
replayed as current truth on later turns.
"""

from __future__ import annotations

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal
from sirah.conversation.core import ConversationCore
from sirah.conversation.fakes import FakeIntentProposer


def _proposer() -> FakeIntentProposer:
    return FakeIntentProposer(
        IntentProposal(IntentName.ANSWER, "sí", EmotionName.FRIENDLY)
    )


def _transcript(text: str) -> Transcript:
    return Transcript(text, 1.0, 2.0, 0.9)


async def test_core_prepends_fresh_vision_context_to_cloud_requests():
    vision = "VISIÓN ACTUAL:\n- Personas visibles: #3."
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: vision)

    await core.respond(_transcript("¿Hay taller de robótica en el Tec?"))

    assert proposer.requests[0].context[0] == vision


async def test_core_does_not_remember_vision_into_turn_memory():
    vision = "VISIÓN ACTUAL:\n- Personas visibles: #3."
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: vision)

    await core.respond(_transcript("¿Me ves?"))
    await core.respond(_transcript("¿Y ahora?"))

    # two turns × (Persona + SIRAH): the vision block is never stored
    assert len(core._context) == 4
    for entry in core._context:
        assert "VISIÓN" not in entry


async def test_core_without_vision_context_is_unaffected():
    proposer = _proposer()
    core = ConversationCore(proposer)

    await core.respond(_transcript("¿Hay taller de robótica en el Tec?"))

    assert proposer.requests[0].context == ()


async def test_core_with_none_vision_context_omits_vision():
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: None)

    await core.respond(_transcript("¿Hay taller de robótica en el Tec?"))

    assert proposer.requests[0].context == ()