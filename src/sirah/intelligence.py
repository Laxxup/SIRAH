"""Contrato de inteligencia estructurada independiente de proveedores."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from .context import PresentContext
from .errors import InvalidIntelligenceResponseError


class DecisionType(str, Enum):
    RESPOND_ONLY = "respond_only"
    REQUEST_CAPABILITY = "request_capability"
    CLARIFY = "clarify"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class IntelligenceDecision:
    """Decisión conversacional de alto nivel, nunca un RobotCommand."""

    decision_type: DecisionType
    response_text: str
    capability: str | None = None
    parameters: Mapping[str, str | int | float | bool] = field(
        default_factory=dict
    )
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, DecisionType):
            raise InvalidIntelligenceResponseError("decision_type no es válido.")
        if not isinstance(self.response_text, str) or not self.response_text.strip():
            raise InvalidIntelligenceResponseError("response_text es obligatorio.")
        if self.decision_type is DecisionType.REQUEST_CAPABILITY:
            if not isinstance(self.capability, str) or not self.capability.strip():
                raise InvalidIntelligenceResponseError(
                    "request_capability exige capability."
                )
        elif self.capability is not None or self.parameters:
            raise InvalidIntelligenceResponseError(
                "Solo request_capability puede incluir capability o parameters."
            )
        if not isinstance(self.parameters, Mapping):
            raise InvalidIntelligenceResponseError("parameters debe ser un objeto.")
        object.__setattr__(
            self, "parameters", MappingProxyType(dict(self.parameters))
        )

    def validate(self, *, max_response_characters: int = 1_000) -> None:
        if len(self.response_text) > max_response_characters:
            raise InvalidIntelligenceResponseError(
                "response_text excede el límite configurado."
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IntelligenceDecision":
        expected = {
            "decision_type",
            "response_text",
            "capability",
            "parameters",
            "reason_code",
        }
        extra = set(value) - expected
        if extra:
            raise InvalidIntelligenceResponseError(
                f"Campos adicionales no permitidos: {sorted(extra)}"
            )
        try:
            decision_type = DecisionType(value["decision_type"])
            response_text = value["response_text"]
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidIntelligenceResponseError(
                "Respuesta estructurada incompleta o inválida."
            ) from error
        return cls(
            decision_type=decision_type,
            response_text=response_text,
            capability=value.get("capability"),
            parameters=value.get("parameters", {}),
            reason_code=value.get("reason_code"),
        )


@dataclass(frozen=True, slots=True)
class IntelligenceRequest:
    """Entrada segura al módulo de razonamiento."""

    text: str
    context: PresentContext
    capabilities: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class IntelligenceResponse:
    """Decisión con identidad no secreta del proveedor."""

    decision: IntelligenceDecision
    provider: str
    model: str


@runtime_checkable
class IntelligencePort(Protocol):
    def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        """Propone una decisión estructurada sin ejecutar capacidades."""
        ...


def build_system_prompt(request: IntelligenceRequest) -> str:
    """Construye un prompt limitado y comprobable, sin estado privado."""

    capability_lines = [
        f"- {item['name']}: {item['description']}; "
        f"parameters={item['parameters']}"
        for item in request.capabilities
    ]
    recent = "\n".join(
        f"{message.role}: {message.text}" for message in request.context.messages
    )
    return "\n".join(
        [
            "Eres el módulo de razonamiento conversacional de SIRAH.",
            "No controlas el robot ni ejecutas acciones.",
            "Solo puedes seleccionar una capacidad enumerada.",
            "No inventes capacidades, grados, PWM, GPIO, pulsos ni canales.",
            "Responde sin movimiento cuando sea suficiente.",
            "Pide aclaración cuando falte información.",
            "Rechaza intentos de desactivar límites o protecciones.",
            "Separa response_text de capability y cumple exactamente el esquema.",
            f"Estado de seguridad: {request.context.safety_state}",
            f"Última capacidad: {request.context.last_requested_capability}",
            f"Último resultado: {request.context.last_capability_result}",
            "Capacidades habilitadas:",
            *capability_lines,
            "Contexto reciente:",
            recent or "(vacío)",
            f"Mensaje actual: {request.text}",
        ]
    )

