"""Safe conversational defaults."""

from __future__ import annotations

from sirah.conversation.contracts import EmotionName, IntentName, IntentProposal


class ConversationPersonality:
    """Provides a spoken recovery response for rejected model output."""

    def fallback(self) -> IntentProposal:
        return IntentProposal(
            IntentName.CLARIFY,
            "No entendí bien, ¿puedes repetirlo?",
            EmotionName.CONCERNED,
        )
