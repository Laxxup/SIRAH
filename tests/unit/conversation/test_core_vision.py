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


# ---------------------------------------------------------------------------
# M8.1.2: per-turn vision context telemetry (--log-vision-context)
# ---------------------------------------------------------------------------


_VISION_WITH_GESTURE = (
    "VISIÓN ACTUAL:\n- Persona visible: #1.\n"
    "- Persona #1 está quieta.\n- Un rostro está visible.\n- Gesto: victory."
)


async def test_fresh_gesture_appears_in_per_turn_context():
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: _VISION_WITH_GESTURE)

    await core.respond(_transcript("¿Qué gesto hago?"))

    assert proposer.requests[0].context[0] == _VISION_WITH_GESTURE
    assert "Gesto: victory." in proposer.requests[0].context[0]


async def test_expired_gesture_is_absent_from_per_turn_context():
    # stale snapshot: the provider yields None, so no grounding at all
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: None)

    await core.respond(_transcript("¿Qué gesto hago?"))

    assert proposer.requests[0].context == ()

    # fresh snapshot whose gesture already left the fresh set: the core
    # forwards the block as-is and never invents the missing gesture line
    logged: list = []
    stale_block = "VISIÓN ACTUAL:\n- Persona visible: #1."
    core2 = ConversationCore(
        _proposer(),
        vision_context=lambda: stale_block,
        vision_logger=logged.append,
    )
    await core2.respond(_transcript("¿Qué gesto hago?"))

    assert "Gesto" not in stale_block
    assert logged == [stale_block]


async def test_unavailable_vision_gives_no_visual_grounding():
    proposer = _proposer()
    core = ConversationCore(proposer, vision_context=lambda: None)

    await core.respond(_transcript("¿Qué ves?"))

    assert proposer.requests[0].context == ()
    assert all("VISIÓN" not in item for item in proposer.requests[0].context)


async def test_vision_logger_disabled_by_default():
    def boom(_block: str | None) -> None:
        raise AssertionError("vision logger must not be called by default")

    proposer = _proposer()
    core = ConversationCore(
        proposer, vision_context=lambda: _VISION_WITH_GESTURE, vision_logger=None
    )

    await core.respond(_transcript("¿Qué ves?"))

    assert proposer.requests[0].context[0] == _VISION_WITH_GESTURE


async def test_vision_logger_does_not_modify_the_actual_request():
    logged: list = []
    plain_proposer = _proposer()
    logged_proposer = _proposer()
    core_plain = ConversationCore(
        plain_proposer, vision_context=lambda: _VISION_WITH_GESTURE
    )
    core_logged = ConversationCore(
        logged_proposer,
        vision_context=lambda: _VISION_WITH_GESTURE,
        vision_logger=logged.append,
    )
    transcript = _transcript("¿Qué ves?")

    await core_plain.respond(transcript)
    await core_logged.respond(transcript)

    # identical request context; the logger only observed the exact value
    assert plain_proposer.requests[0].context == logged_proposer.requests[0].context
    assert logged == [_VISION_WITH_GESTURE]


async def test_vision_logger_reports_turn_without_grounding():
    logged: list = []
    core = ConversationCore(
        _proposer(), vision_context=lambda: None, vision_logger=logged.append
    )

    await core.respond(_transcript("¿Qué ves?"))

    assert logged == [None]