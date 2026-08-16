"""Safe conversational defaults."""

from __future__ import annotations

from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal

UNDERSTANDING_FALLBACK_SPEECH = "No te entendí bien, ¿puedes repetirlo?"
GENERATION_FALLBACK_SPEECH = (
    "Tuve un problema al preparar la respuesta. ¿Puedes intentarlo otra vez?"
)
INVALID_RESPONSE_FALLBACK_SPEECH = (
    "No pude formular bien la respuesta. Inténtalo de nuevo."
)


class ConversationPersonality:
    """Provides deterministic spoken recovery for rejected input, provider
    failures and invalid model output."""

    def understanding_fallback(self) -> IntentProposal:
        """The user's input could not be understood; ask them to repeat it."""
        return IntentProposal(
            IntentName.CLARIFY,
            UNDERSTANDING_FALLBACK_SPEECH,
            EmotionName.CONCERNED,
        )

    def generation_fallback(self) -> IntentProposal:
        """The response could not be produced (timeout or provider failure)."""
        return IntentProposal(
            IntentName.CLARIFY,
            GENERATION_FALLBACK_SPEECH,
            EmotionName.CONCERNED,
        )

    def invalid_response_fallback(self) -> IntentProposal:
        """Model output was rejected after the bounded repair path."""
        return IntentProposal(
            IntentName.CLARIFY,
            INVALID_RESPONSE_FALLBACK_SPEECH,
            EmotionName.CONCERNED,
        )

    def fallback(self) -> IntentProposal:
        """Backward-compatible alias for :meth:`understanding_fallback`."""
        return self.understanding_fallback()
