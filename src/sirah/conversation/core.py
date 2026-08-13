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
        context_limit: int = 12,
    ) -> None:
        self._proposer = proposer
        self._clock = clock
        self._minimum_confidence = minimum_confidence
        self._context: deque[str] = deque(maxlen=context_limit)

    async def respond(self, transcript: Transcript) -> IntentProposal:
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
        normalized = text.lower()
        if normalized.strip(".,¡!¿? ") in {"ah ok", "ah ok ok", "ok", "okay", "está bien", "esta bien", "bueno", "gracias"}:
            return IntentProposal(
                IntentName.ACKNOWLEDGE,
                "Me alegra. Si quieres, podemos seguir conversando o probar otra cosa.",
                EmotionName.FRIENDLY,
            )
        if "tec" in normalized and any(word in normalized for word in ("taller", "curso", "club", "actividad", "evento")):
            return IntentProposal(
                IntentName.CLARIFY,
                "No tengo confirmación de actividades específicas del Tec. Te recomiendo preguntar en tu facultad o revisar sus canales oficiales; seguro encontrarás opciones para explorar robótica.",
                EmotionName.CURIOUS,
            )
        if any(phrase in normalized for phrase in ("te puedes presentar", "puedes presentarte", "quién eres", "quien eres")):
            return IntentProposal(
                IntentName.ANSWER,
                "Soy SIRAH, un proyecto universitario de robótica e inteligencia artificial. Puedo escucharte y conversar contigo por voz; si te interesa conocer cómo estoy construida, mi repositorio está en GitHub: github.com/Laxxup/SIRAH.",
                EmotionName.FRIENDLY,
            )
        if any(phrase in normalized for phrase in ("quiero probarte", "probar el proyecto", "aportar ideas", "quiero colaborar", "ver el repositorio", "tu repositorio")):
            return IntentProposal(
                IntentName.ANSWER,
                "Me alegra que quieras conocerme mejor. Puedes probar mi proyecto, revisar cómo está construido y aportar ideas en github.com/Laxxup/SIRAH.",
                EmotionName.CURIOUS,
            )
        if "cómo te llamas" in normalized or "que significa sirah" in normalized or "qué significa sirah" in normalized:
            return IntentProposal(IntentName.ANSWER, "Me llamo SIRAH, Sistema Inteligente Robótico de Asistencia Humana.", EmotionName.FRIENDLY)
        if "hora" in normalized:
            return IntentProposal(IntentName.ANSWER, f"Son las {self._clock():%H:%M}.", EmotionName.FRIENDLY)
        if "me escuchas" in normalized or "si me escuchas" in normalized:
            return IntentProposal(IntentName.ANSWER, "Sí, te escucho. ¿En qué puedo ayudarte?", EmotionName.FRIENDLY)
        if "fecha" in normalized or "día" in normalized or "dia" in normalized:
            return IntentProposal(IntentName.ANSWER, f"Hoy es {self._clock():%Y-%m-%d}.", EmotionName.FRIENDLY)
        if "cómo estás" in normalized or "como estas" in normalized:
            return IntentProposal(IntentName.ANSWER, "Estoy disponible para ayudarte. ¿Qué necesitas?", EmotionName.FRIENDLY)
        if any(phrase in normalized for phrase in ("qué puedes hacer", "que puedes hacer", "qué te falta", "que te falta", "qué quieres lograr", "que quieres lograr", "tus capacidades", "tus limitaciones")):
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


def _is_spanish(speech: str | None) -> bool:
    if not speech:
        return True
    words = {word.strip(".,¿?¡!").lower() for word in speech.split()}
    return bool(words & {"el", "la", "de", "que", "no", "puedes", "sirah", "son", "hola", "tienes", "manzanas", "gracias", "puedo", "sí", "te", "escucho", "ayudarte"})


def _claims_wrong_identity(speech: str | None) -> bool:
    return bool(speech and ("chatgpt" in speech.lower() or "openai" in speech.lower()))
