"""Bounded in-memory conversation context."""

from __future__ import annotations

from collections import deque
from sirah.types import ConversationMessage, PresentContext

__all__ = ["ConversationContext"]


class ConversationContext:
    def __init__(self, max_messages: int = 16, max_chars: int = 4096) -> None:
        self._messages: deque[ConversationMessage] = deque(maxlen=max_messages)
        self._max_chars = max_chars
        self._present = PresentContext()

    def add(self, message: ConversationMessage) -> None:
        self._messages.append(message)
        self._trim()

    def _trim(self) -> None:
        total = sum(len(m.content) for m in self._messages)
        while total > self._max_chars and len(self._messages) > 2:
            removed = self._messages.popleft()
            total -= len(removed.content)

    @property
    def messages(self) -> tuple[ConversationMessage, ...]:
        return tuple(self._messages)

    @property
    def last_user_text(self) -> str | None:
        for m in reversed(self._messages):
            if m.role == "user":
                return m.content
        return None

    @property
    def present(self) -> PresentContext:
        return self._present

    @present.setter
    def present(self, value: PresentContext) -> None:
        self._present = value

    @property
    def is_empty(self) -> bool:
        return len(self._messages) == 0

    def clear(self) -> None:
        self._messages.clear()
        self._present = PresentContext()
