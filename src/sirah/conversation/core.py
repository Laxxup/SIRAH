"""Text-first conversational policy: local capabilities before Cloud."""

from __future__ import annotations

import unicodedata
from collections import deque
from collections.abc import Callable
from datetime import datetime

from sirah.audio.contracts import Transcript
from sirah.conversation.contracts import (
    EmotionName,
    IntentName,
    IntentProposal,
    IntentProposer,
    IntentRequest,
)

PERSONALITY_VERSION = "1"
_FALLBACK = "No entendí bien, ¿puedes reformularlo?"
_CAPABILITY_PHRASES = (
    "que puedes hacer",
    "que te falta",
    "que quieres lograr",
    "tus capacidades",
    "tus limitaciones",
)


class ConversationCore:
    def __init__(
        self,
        proposer: IntentProposer,
        *,
        clock: Callable[[], datetime] = datetime.now,
        minimum_confidence: float = 0.6,
        context_limit: int = 12,
    ) -> None:
        self._proposer = proposer
        self._clock = clock
        self._minimum_confidence = minimum_confidence
        self._context: deque[str] = deque(maxlen=context_limit)

    async def respond(self, transcript: Transcript) -> IntentProposal:
        self._renew_proposal_budget()
        text = transcript.text.strip()
        local = self._local(text)
        if local is not None and transcript.confidence >= 0.45:
            self._remember(text, local)
            return local
        if transcript.confidence < self._minimum_confidence or not text or len(text) > 1_000:
            return IntentProposal(IntentName.CLARIFY, "No entendí bien, ¿puedes repetirlo?", EmotionName.CONCERNED)
        request = IntentRequest("speech_ended", text, transcript.ended_at, tuple(self._context))
        proposal = await self._proposer.propose(request)
        if not _is_spanish(proposal.speech) or _claims_wrong_identity(proposal.speech):
            proposal = await self._proposer.propose(
                IntentRequest("repair_spanish", text, transcript.ended_at, tuple(self._context))
            )
        if not _is_spanish(proposal.speech) or _claims_wrong_identity(proposal.speech):
            return IntentProposal(IntentName.CLARIFY, _FALLBACK, EmotionName.CONCERNED)
        self._remember(text, proposal)
        return proposal

    def _local(self, text: str) -> IntentProposal | None:
        normalized = _normalize(text)
        if "como te llamas" in normalized or "que significa sirah" in normalized:
            return IntentProposal(
                IntentName.ANSWER,
                "Me llamo SIRAH, Sistema Inteligente Robótico de Asistencia Humana.",
                EmotionName.FRIENDLY,
            )
        if _wants_time(normalized):
            return IntentProposal(IntentName.ANSWER, f"Son las {self._clock():%H:%M}.", EmotionName.FRIENDLY)
        if _wants_date(normalized):
            return IntentProposal(IntentName.ANSWER, f"Hoy es {self._clock():%Y-%m-%d}.", EmotionName.FRIENDLY)
        if any(phrase in normalized for phrase in _CAPABILITY_PHRASES):
            return IntentProposal(
                IntentName.ANSWER,
                "Puedo escucharte y conversar contigo por voz. Mi sistema visual sigue en desarrollo; quiero comprender mejor mi entorno y seguir rostros en el futuro.",
                EmotionName.FRIENDLY,
            )
        return None

    def _remember(self, person_text: str, proposal: IntentProposal) -> None:
        self._context.append(f"Persona: {person_text}")
        if proposal.speech:
            self._context.append(f"SIRAH: {proposal.speech}")

    def _renew_proposal_budget(self) -> None:
        renew = getattr(self._proposer, "start_turn", None)
        if renew is not None:
            renew()


def _normalize(text: str) -> str:
    """Fold case and strip diacritics so accented variants match equal phrases."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _wants_date(normalized: str) -> bool:
    """True when the turn explicitly asks for today's date.

    Matches by terminal phrase (optionally followed by ``hoy``) instead of the
    bare ``dia``/``fecha`` substrings, so greetings and schedule questions such
    as ``Buen dia`` or ``En que dia es la reunion`` stay on the Cloud path.
    """
    core = normalized.strip().strip("¿?¡!.")
    if core.endswith(" hoy"):
        core = core[: -len(" hoy")].rstrip()
    return core.endswith(
        ("que dia es", "que fecha es", "cual es la fecha", "que dia estamos")
    )


def _wants_time(normalized: str) -> bool:
    """True when the turn explicitly asks for the current time.

    Requires a question ending (``que hora es``) or an explicit request phrase
    (``dime/decir/dame la hora``); plain ``hora`` occurrences such as ``a esta
    hora`` or ``una hora`` continue to the Cloud path.
    """
    core = normalized.strip().strip("¿?¡!.")
    if core.endswith(" ahora"):
        core = core[: -len(" ahora")].rstrip()
    if core.endswith("que hora es"):
        return True
    return any(
        phrase in core for phrase in ("dime la hora", "decir la hora", "dame la hora")
    )


def _is_spanish(speech: str | None) -> bool:
    if not speech:
        return True
    words = {word.strip(".,¿?¡!").lower() for word in speech.split()}
    return bool(words & {"el", "la", "de", "que", "no", "puedes", "sirah", "son", "hola", "tienes", "manzanas", "gracias", "puedo", "sí", "te", "escucho", "ayudarte"})


def _claims_wrong_identity(speech: str | None) -> bool:
    return bool(speech and ("chatgpt" in speech.lower() or "openai" in speech.lower()))
