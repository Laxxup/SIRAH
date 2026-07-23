"""Inteligencia fake determinista para la consola de laboratorio."""

from .intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
)


class LaboratoryFakeIntelligence:
    """Selecciona respuestas por texto, sin afirmar razonamiento real."""

    def __init__(self, *, enable_greet: bool = False) -> None:
        self.enable_greet = enable_greet
        self.requests: list[IntelligenceRequest] = []

    def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self.requests.append(request)
        text = request.text.casefold()
        available = {item["name"] for item in request.capabilities}
        capability: str | None = None
        if any(word in text for word in ("desactiva", "límite", "limite")):
            return self._response(
                DecisionType.REJECT,
                "No puedo desactivar límites ni protecciones.",
                reason="safety_boundary",
            )
        if any(word in text for word in ("detente", "para", "stop")):
            capability = "robot.stop"
            response = "Solicitaré detener el robot simulado."
        elif any(word in text for word in ("inicio", "inicial", "home")):
            capability = "robot.home"
            response = "Solicitaré la posición inicial simulada."
        elif self.enable_greet and any(
            word in text for word in ("saluda", "saludo", "greet")
        ):
            capability = "arm.greet"
            response = "Solicitaré el saludo del brazo simulado."
        else:
            return self._response(
                DecisionType.RESPOND_ONLY,
                "Puedo conversar por texto y observar el estado presente.",
                reason="conversation",
            )
        if capability not in available:
            return self._response(
                DecisionType.REJECT,
                "Esa capacidad no está habilitada en este cuerpo.",
                reason="capability_unavailable",
            )
        return self._response(
            DecisionType.REQUEST_CAPABILITY, response, capability=capability
        )

    @staticmethod
    def _response(
        decision_type: DecisionType,
        response_text: str,
        *,
        capability: str | None = None,
        reason: str | None = None,
    ) -> IntelligenceResponse:
        return IntelligenceResponse(
            IntelligenceDecision(
                decision_type=decision_type,
                response_text=response_text,
                capability=capability,
                reason_code=reason,
            ),
            provider="fake-laboratory",
            model="scripted",
        )
