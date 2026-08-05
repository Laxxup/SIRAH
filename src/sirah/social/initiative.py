"""Initiative evaluation — pure function for greeting decisions."""

from __future__ import annotations

from sirah.types import InitiativeDecision, InitiativeAction, PerceptionFrame
from sirah.social.memory import InteractionMemory

__all__ = ["evaluate_initiative"]


def evaluate_initiative(
    frame: PerceptionFrame,
    memory: InteractionMemory,
    active_conversation: bool = False,
) -> InitiativeDecision:
    if not frame.faces:
        return InitiativeDecision(
            action=InitiativeAction.SILENT,
            reason="no faces detected",
        )

    if active_conversation:
        return InitiativeDecision(
            action=InitiativeAction.SILENT,
            reason="conversation in progress",
        )

    if not memory.can_greet:
        return InitiativeDecision(
            action=InitiativeAction.SILENT,
            reason="cooldown active",
        )

    face_count = len(frame.faces)
    best_conf = max((f.confidence for f in frame.faces), default=0.0)

    if memory.is_empty or memory.greet_count == 0:
        return InitiativeDecision(
            action=InitiativeAction.GREET,
            text="¡Hola! Soy SIRAH. ¿En qué puedo ayudarte?",
            reason=f"first greeting, {face_count} face(s), conf={best_conf:.2f}",
        )

    return InitiativeDecision(
        action=InitiativeAction.CHECK_IN,
        text="Hola de nuevo. ¿Todo bien?",
        reason=f"returning person, {face_count} face(s)",
    )
