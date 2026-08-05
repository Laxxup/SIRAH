"""InteractionMemory — social memory with sliding window."""

from __future__ import annotations

from time import monotonic

__all__ = ["InteractionMemory"]


class InteractionMemory:
    def __init__(self, max_entries: int = 128, cooldown_s: float = 30.0) -> None:
        self._entries: list[str] = []
        self._max_entries = max_entries
        self._cooldown_s = cooldown_s
        self._last_greet: float = 0.0
        self._greet_count: int = 0

    def record(self, entry: str) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2 :]

    def mark_greet(self) -> None:
        self._last_greet = monotonic()
        self._greet_count += 1

    @property
    def last_greet(self) -> float:
        return self._last_greet

    @property
    def greet_count(self) -> int:
        return self._greet_count

    @property
    def entries(self) -> tuple[str, ...]:
        return tuple(self._entries)

    @property
    def cooldown_s(self) -> float:
        return self._cooldown_s

    @property
    def can_greet(self) -> bool:
        if self._last_greet == 0:
            return True
        return (monotonic() - self._last_greet) >= self._cooldown_s

    @property
    def is_empty(self) -> bool:
        return len(self._entries) == 0
