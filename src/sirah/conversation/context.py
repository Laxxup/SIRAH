"""Bounded, process-local context for a conversation session."""

from __future__ import annotations

from collections import deque

from sirah.audio.contracts import Transcript


class ConversationContext:
    """Retain only the most recent transcript turns for the active process."""

    def __init__(self, limit: int = 8) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self._transcripts: deque[Transcript] = deque(maxlen=limit)

    @property
    def transcripts(self) -> tuple[Transcript, ...]:
        return tuple(self._transcripts)

    def add(self, transcript: Transcript) -> None:
        self._transcripts.append(transcript)
