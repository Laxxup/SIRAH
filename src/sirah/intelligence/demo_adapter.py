"""Laboratory intelligence — rule-based keyword matching for dev console."""

from __future__ import annotations

from time import monotonic

from sirah.types import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
)

__all__ = ["LaboratoryIntelligence"]

GREET_PATTERNS = ("hola", "buenos", "saludos", "hey", "qué tal", "como estas")
FAREWELL_PATTERNS = ("adiós", "chau", "hasta luego", "nos vemos")
STOP_PATTERNS = ("para", "detente", "stop", "alto")


class LaboratoryIntelligence:
    def __init__(self) -> None:
        self._counter = 0

    async def health(self) -> bool:
        return True

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        t0 = monotonic()
        self._counter += 1

        last = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                last = msg.content.lower().strip()
                break

        text = self._classify(last)

        return IntelligenceResponse(
            raw_text=text,
            decision=IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=text,
                confidence=1.0,
            ),
            latency_ms=(monotonic() - t0) * 1000,
            model="laboratory",
        )

    def _classify(self, text: str) -> str:
        if not text:
            return "No te he oído. ¿Puedes repetir?"

        if any(w in text for w in STOP_PATTERNS):
            return "Deteniéndome."

        if any(w in text for w in GREET_PATTERNS):
            return "¡Hola! Soy SIRAH, tu asistente robótico. ¿En qué puedo ayudarte?"

        if any(w in text for w in FAREWELL_PATTERNS):
            return "¡Hasta luego! Que tengas un buen día."

        return f"Entendido. [{self._counter}] Procesado: {text[:50]}"
