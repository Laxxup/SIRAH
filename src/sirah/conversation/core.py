"""Text-first conversational policy: local capabilities before Cloud."""

from __future__ import annotations

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


class ConversationCore:
    def __init__(
        self,
        proposer: IntentProposer,
        *,
        clock: Callable[[], datetime] = datetime.now,
        minimum_confidence: float = 0.6,
        context_limit: int = 6,
    ) -> None:
        self._proposer = proposer
        self._clock = clock
        self._minimum_confidence = minimum_confidence
        self._context: deque[str] = deque(maxlen=context_limit)

    async def respond(self, transcript: Transcript) -> IntentProposal:
        text = transcript.text.strip()
        if transcript.confidence < self._minimum_confidence or not text or len(text) > 1_000:
            return IntentProposal(IntentName.CLARIFY, "No entendí bien, ¿puedes repetirlo?", EmotionName.CONCERNED)
        local = self._local(text)
        if local is not None:
            self._context.append(text)
            return local
        request = IntentRequest("speech_ended", text, transcript.ended_at, tuple(self._context))
        proposal = await self._proposer.propose(request)
        if not _is_spanish(proposal.speech) or _claims_wrong_identity(proposal.speech):
            proposal = await self._proposer.propose(
                IntentRequest("repair_spanish", text, transcript.ended_at, tuple(self._context))
            )
        if not _is_spanish(proposal.speech) or _claims_wrong_identity(proposal.speech):
            return IntentProposal(IntentName.CLARIFY, _FALLBACK, EmotionName.CONCERNED)
        self._context.append(text)
        return proposal

    def _local(self, text: str) -> IntentProposal | None:
        normalized = text.lower()
        if "cómo te llamas" in normalized or "que significa sirah" in normalized or "qué significa sirah" in normalized:
            return IntentProposal(IntentName.ANSWER, "Me llamo SIRAH, Sistema Inteligente Robótico de Asistencia Humana.", EmotionName.FRIENDLY)
        if "hora" in normalized:
            return IntentProposal(IntentName.ANSWER, f"Son las {self._clock():%H:%M}.", EmotionName.FRIENDLY)
        if "fecha" in normalized or "día" in normalized or "dia" in normalized:
            return IntentProposal(IntentName.ANSWER, f"Hoy es {self._clock():%Y-%m-%d}.", EmotionName.FRIENDLY)
        return None


def _is_spanish(speech: str | None) -> bool:
    if not speech:
        return True
    words = {word.strip(".,¿?¡!").lower() for word in speech.split()}
    return bool(words & {"el", "la", "de", "que", "no", "puedes", "sirah", "son", "hola", "tienes", "manzanas", "gracias", "puedo"})


def _claims_wrong_identity(speech: str | None) -> bool:
    return bool(speech and ("chatgpt" in speech.lower() or "openai" in speech.lower()))
