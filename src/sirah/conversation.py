"""Orquestación conversacional segura de texto a capacidad."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import count

from .capabilities import CapabilityCatalog, CapabilityRequest
from .context import ConversationMessage, SessionContextStore
from .cortex_integration import CapabilityExecutionResult, CapabilityRunner
from .errors import (
    CapabilityRejectedError,
    IntelligenceError,
    InvalidIntelligenceResponseError,
)
from .intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligencePort,
    IntelligenceRequest,
)


@dataclass(frozen=True, slots=True)
class ConversationResult:
    """Resultado completo para consumidores de la aplicación."""

    response_text: str
    decision: IntelligenceDecision | None
    requested_capability: str | None
    capability_executed: bool
    mechanical_result: CapabilityExecutionResult | None
    safe_error: str | None
    provider: str
    model: str


class ConversationOrchestrator:
    """Mantiene la autoridad entre inteligencia y ejecución mecánica."""

    def __init__(
        self,
        *,
        intelligence: IntelligencePort,
        catalog: CapabilityCatalog,
        runner: CapabilityRunner,
        contexts: SessionContextStore,
        max_response_characters: int = 1_000,
    ) -> None:
        self._intelligence = intelligence
        self._catalog = catalog
        self._runner = runner
        self._contexts = contexts
        self._max_response_characters = max_response_characters
        self._request_numbers = count(1)

    def handle(self, session_id: str, text: str) -> ConversationResult:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("El mensaje debe ser una cadena no vacía.")
        self._contexts.append(session_id, ConversationMessage("user", text))
        context = self._contexts.get(session_id)
        request = IntelligenceRequest(
            text=text,
            context=context,
            capabilities=self._catalog.safe_prompt_view(),
        )
        try:
            intelligence_response = self._intelligence.decide(request)
            decision = intelligence_response.decision
            decision.validate(
                max_response_characters=self._max_response_characters
            )
        except (IntelligenceError, InvalidIntelligenceResponseError) as error:
            message = (
                "No pude consultar el razonamiento de forma segura. "
                "No se ejecutó ninguna acción."
            )
            self._contexts.append(
                session_id, ConversationMessage("assistant", message)
            )
            return ConversationResult(
                response_text=message,
                decision=None,
                requested_capability=None,
                capability_executed=False,
                mechanical_result=None,
                safe_error=f"{type(error).__name__}: {error}",
                provider="unavailable",
                model="unavailable",
            )

        if decision.decision_type is not DecisionType.REQUEST_CAPABILITY:
            self._contexts.append(
                session_id,
                ConversationMessage("assistant", decision.response_text),
            )
            return ConversationResult(
                response_text=decision.response_text,
                decision=decision,
                requested_capability=None,
                capability_executed=False,
                mechanical_result=None,
                safe_error=None,
                provider=intelligence_response.provider,
                model=intelligence_response.model,
            )

        capability = decision.capability
        if capability is None:
            raise InvalidIntelligenceResponseError(
                "La decisión mecánica carece de capability."
            )
        capability_request = CapabilityRequest(
            request_id=f"{session_id}:{next(self._request_numbers)}",
            capability=capability,
            parameters=decision.parameters,
        )
        try:
            mechanical = self._runner.run(capability_request)
        except CapabilityRejectedError as error:
            message = (
                f"{decision.response_text} La solicitud fue rechazada por "
                "la política local y no se ejecutó."
            )
            self._contexts.update_action(
                session_id, capability=capability, result="rejected"
            )
            self._contexts.append(
                session_id, ConversationMessage("assistant", message)
            )
            return ConversationResult(
                response_text=message,
                decision=decision,
                requested_capability=capability,
                capability_executed=False,
                mechanical_result=None,
                safe_error=f"{type(error).__name__}: {error}",
                provider=intelligence_response.provider,
                model=intelligence_response.model,
            )

        status = "succeeded" if mechanical.succeeded else "failed"
        self._contexts.update_action(
            session_id, capability=capability, result=status
        )
        if mechanical.succeeded:
            message = decision.response_text
            safe_error = None
        else:
            message = (
                f"{decision.response_text} La entrega mecánica falló; "
                "no debe considerarse completada."
            )
            safe_error = mechanical.error
        self._contexts.append(
            session_id, ConversationMessage("assistant", message)
        )
        return ConversationResult(
            response_text=message,
            decision=decision,
            requested_capability=capability,
            capability_executed=mechanical.succeeded,
            mechanical_result=mechanical,
            safe_error=safe_error,
            provider=intelligence_response.provider,
            model=intelligence_response.model,
        )

