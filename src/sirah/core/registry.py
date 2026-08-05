"""Component registry for observable system state."""

from __future__ import annotations

from time import monotonic
from sirah.types import (
    ComponentId,
    ComponentKind,
    ComponentState,
    ComponentStatus,
    SystemSnapshot,
    ConversationResult,
)

__all__ = ["ComponentRegistry"]


class ComponentRegistry:
    def __init__(self) -> None:
        self._states: dict[ComponentId, ComponentState] = {}
        self._results: list[ConversationResult] = []

    def register(self, kind: ComponentKind, name: str) -> ComponentId:
        cid = ComponentId(kind=kind, name=name)
        self._states[cid] = ComponentState(id=cid)
        return cid

    def update(self, cid: ComponentId, status: ComponentStatus, detail: str = "") -> None:
        self._states[cid] = ComponentState(id=cid, status=status, detail=detail)

    def record_result(self, result: ConversationResult) -> None:
        self._results.append(result)
        if len(self._results) > 256:
            self._results = self._results[-128:]

    @property
    def last_results(self) -> tuple[ConversationResult, ...]:
        return tuple(self._results[-20:])

    def snapshot(self) -> SystemSnapshot:
        return SystemSnapshot(
            components=tuple(self._states.values()),
            timestamp=monotonic(),
        )

    def component_status(self, cid: ComponentId) -> ComponentStatus:
        return self._states.get(cid, ComponentState(id=cid)).status
