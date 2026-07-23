"""Contexto presente, acotado y exclusivamente en memoria."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """Mensaje reciente apto para contexto conversacional."""

    role: str
    text: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise ValueError("role debe ser user o assistant.")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text debe ser una cadena no vacía.")


@dataclass(frozen=True, slots=True)
class PresentContext:
    """Fotografía limitada de una sesión, sin memoria persistente."""

    session_id: str
    messages: tuple[ConversationMessage, ...] = ()
    summary: str | None = None
    last_requested_capability: str | None = None
    last_capability_result: str | None = None
    safety_state: str = "normal"
    current_task: str | None = None


class SessionContextStore:
    """Almacén determinista de contexto que desaparece con la instancia."""

    def __init__(
        self, *, max_messages: int = 8, max_characters: int = 4_000
    ) -> None:
        if max_messages < 1 or max_characters < 1:
            raise ValueError("Los límites de contexto deben ser positivos.")
        self._max_messages = max_messages
        self._max_characters = max_characters
        self._sessions: dict[str, PresentContext] = {}

    def get(self, session_id: str) -> PresentContext:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id debe ser una cadena no vacía.")
        return self._sessions.get(session_id, PresentContext(session_id=session_id))

    def clear(self, session_id: str) -> PresentContext:
        """Reinicia el contexto temporal de una sesión y lo devuelve vacío."""

        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id debe ser una cadena no vacía.")
        context = PresentContext(session_id=session_id)
        self._sessions[session_id] = context
        return context

    def append(self, session_id: str, message: ConversationMessage) -> PresentContext:
        context = self.get(session_id)
        messages = self._trim((*context.messages, message))
        updated = replace(context, messages=messages)
        self._sessions[session_id] = updated
        return updated

    def update_action(
        self,
        session_id: str,
        *,
        capability: str | None,
        result: str,
    ) -> PresentContext:
        context = self.get(session_id)
        updated = replace(
            context,
            last_requested_capability=capability,
            last_capability_result=result,
        )
        self._sessions[session_id] = updated
        return updated

    def set_safety_state(self, session_id: str, state: str) -> PresentContext:
        if state not in {"normal", "degraded", "emergency"}:
            raise ValueError("Estado de seguridad desconocido.")
        context = replace(self.get(session_id), safety_state=state)
        self._sessions[session_id] = context
        return context

    def _trim(
        self, messages: tuple[ConversationMessage, ...]
    ) -> tuple[ConversationMessage, ...]:
        kept = list(messages[-self._max_messages :])
        while kept and sum(len(item.text) for item in kept) > self._max_characters:
            kept.pop(0)
        return tuple(kept)
