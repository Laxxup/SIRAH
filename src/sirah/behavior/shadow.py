"""In-memory audit log for proposals that have no execution authority."""

from __future__ import annotations

from sirah.behavior.future_contracts import BehaviorEvent, ProposalResult


class ShadowLog:
    def __init__(self) -> None:
        self._records: list[tuple[BehaviorEvent, ProposalResult]] = []

    def record(self, event: BehaviorEvent, result: ProposalResult) -> None:
        self._records.append((event, result))

    def records(self) -> tuple[tuple[BehaviorEvent, ProposalResult], ...]:
        return tuple(self._records)
