"""Pure contracts for the future behavior and LLM boundary.

These types carry semantic events and shadow-only decisions. They intentionally
have no dependency on perception implementations, runtime, transport, or
hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EventKind(str, Enum):
    PERSON_ARRIVED = "person_arrived"
    PERSON_LOST = "person_lost"


class ActionKind(str, Enum):
    """Actions allowed during the shadow-only phase."""

    NO_OP = "no_op"


class RejectionReason(str, Enum):
    UNKNOWN_INTENT = "unknown_intent"
    INCOMPATIBLE_STATE = "incompatible_state"
    COOLDOWN = "cooldown"
    SHADOW_ONLY = "shadow_only"


@dataclass(frozen=True)
class BehaviorEvent:
    kind: EventKind
    observed_at: float


@dataclass(frozen=True)
class SirahIntent:
    """A closed, future LLM proposal tied to its triggering event."""

    name: str
    event: BehaviorEvent


@dataclass(frozen=True)
class ValidatedAction:
    """A policy result with no authority to affect physical systems."""

    kind: ActionKind
    reason: str


@dataclass(frozen=True)
class ProposalResult:
    """An accepted action or a rejection, never both."""

    action: ValidatedAction | None = None
    rejection: RejectionReason | None = None

    def __post_init__(self) -> None:
        if (self.action is None) == (self.rejection is None):
            raise ValueError("ProposalResult requires exactly one outcome")

    @classmethod
    def accepted(cls, action: ValidatedAction) -> ProposalResult:
        return cls(action=action)

    @classmethod
    def rejected(cls, reason: RejectionReason) -> ProposalResult:
        return cls(rejection=reason)
