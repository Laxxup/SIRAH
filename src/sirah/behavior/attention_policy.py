"""Deterministic, shadow-only behavior policy."""

from __future__ import annotations

from dataclasses import dataclass

from sirah.behavior.future_contracts import ActionKind, BehaviorEvent, ValidatedAction


@dataclass(frozen=True)
class PolicyDecision:
    action: ValidatedAction


class BehaviorPolicy:
    """Maps semantic edges to auditable no-op decisions in the first phase."""

    def decide(self, event: BehaviorEvent) -> PolicyDecision:
        return PolicyDecision(ValidatedAction(ActionKind.NO_OP, event.kind.value))
