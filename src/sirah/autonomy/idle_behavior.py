"""IdleBehavior — autonomous actions when no user interaction."""

from __future__ import annotations

from enum import Enum, auto
from time import monotonic

__all__ = ["IdleBehavior", "IdleAction", "IdleState"]


class IdleAction(Enum):
    LOOK_AROUND = auto()
    AMBIENT_COMMENT = auto()
    CURIOSITY_CHECK = auto()
    REST = auto()
    SCAN_FOR_FACES = auto()


IDLE_COMMENTS = [
    "Qué bonito día hace hoy.",
    "Me pregunto qué estará pasando en el mundo.",
    "Hace un rato que no veo a nadie.",
    "Todo tranquilo por aquí.",
    "¿Habrá alguien por ahí?",
    "Me gusta cuando hay gente cerca.",
]


class IdleState:
    def __init__(self, idle_threshold_s: float = 60.0) -> None:
        self._last_interaction = monotonic()
        self._idle_threshold = idle_threshold_s
        self._comment_index = 0
        self._last_action_time = 0.0
        self._action_cooldown = 10.0

    @property
    def is_idle(self) -> bool:
        return (monotonic() - self._last_interaction) > self._idle_threshold

    @property
    def idle_duration(self) -> float:
        return monotonic() - self._last_interaction

    def mark_interaction(self) -> None:
        self._last_interaction = monotonic()

    def next_action(self) -> IdleAction | None:
        if not self.is_idle:
            return None
        if monotonic() - self._last_action_time < self._action_cooldown:
            return None
        self._last_action_time = monotonic()
        return IdleAction.AMBIENT_COMMENT

    def get_comment(self) -> str:
        comment = IDLE_COMMENTS[self._comment_index % len(IDLE_COMMENTS)]
        self._comment_index += 1
        return comment

    def reset(self) -> None:
        self._last_interaction = monotonic()
        self._comment_index = 0
        self._last_action_time = 0.0


class IdleBehavior:
    def __init__(self, idle_threshold_s: float = 60.0) -> None:
        self._state = IdleState(idle_threshold_s=idle_threshold_s)
        self._action_history: list[tuple[float, IdleAction, str]] = []

    def mark_active(self) -> None:
        self._state.mark_interaction()

    def tick(self) -> tuple[IdleAction, str] | None:
        action = self._state.next_action()
        if action is None:
            return None

        if action == IdleAction.AMBIENT_COMMENT:
            comment = self._state.get_comment()
            self._action_history.append((monotonic(), action, comment))
            return (action, comment)

        return None

    def reset(self) -> None:
        self._state.reset()
        self._action_history.clear()

    @property
    def history(self) -> tuple[tuple[float, IdleAction, str], ...]:
        return tuple(self._action_history)

    @property
    def is_idle(self) -> bool:
        return self._state.is_idle
