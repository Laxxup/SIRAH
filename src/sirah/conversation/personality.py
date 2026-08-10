"""Safe conversational defaults."""

from __future__ import annotations

from sirah.conversation.contracts import IntentName, IntentProposal


class ConversationPersonality:
    """Provides the non-speaking fallback used for rejected model output."""

    def fallback(self) -> IntentProposal:
        return IntentProposal(IntentName.SILENT, None)
