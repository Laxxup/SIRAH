"""Closed intent contracts for shadow-mode conversation proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Protocol, runtime_checkable


class IntentName(str, Enum):
    ANSWER = "answer"
    ACKNOWLEDGE = "acknowledge"
    CLARIFY = "clarify"
    SILENT = "silent"


class EmotionName(str, Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    CURIOUS = "curious"
    CONCERNED = "concerned"


class ActionName(str, Enum):
    NONE = "none"


@dataclass(frozen=True)
class IntentRequest:
    """Derived text only; raw audio, frames, memory, and commands are excluded."""

    event: str
    text: str | None
    observed_at: float

    def __post_init__(self) -> None:
        if not isinstance(self.event, str):
            raise TypeError("event must be text")
        if not isinstance(self.text, (str, type(None))):
            raise TypeError("text must be text or None")
        if not self.event:
            raise ValueError("event must not be empty")
        if not isfinite(self.observed_at):
            raise ValueError("observed_at must be finite")


@dataclass(frozen=True)
class IntentProposal:
    intent: IntentName
    speech: str | None
    emotion: EmotionName = EmotionName.NEUTRAL
    action: ActionName = ActionName.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.intent, IntentName):
            raise TypeError("intent must be an IntentName")
        if not isinstance(self.speech, (str, type(None))):
            raise TypeError("speech must be text or None")
        if not isinstance(self.emotion, EmotionName):
            raise TypeError("emotion must be an EmotionName")
        if not isinstance(self.action, ActionName):
            raise TypeError("action must be an ActionName")
        if self.intent is IntentName.SILENT and self.speech is not None:
            raise ValueError("silent intent must not include speech")
        if self.intent is not IntentName.SILENT and not self.speech:
            raise ValueError("spoken intents require speech")


@runtime_checkable
class IntentProposer(Protocol):
    async def propose(self, request: IntentRequest) -> IntentProposal: ...
