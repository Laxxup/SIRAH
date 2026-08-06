"""Fake intelligence — deterministic responses for testing."""

from __future__ import annotations

from time import monotonic

from sirah.types import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceRequest,
    IntelligenceResponse,
)

__all__ = ["FakeIntelligence"]


class FakeIntelligence:
    def __init__(self, scripted: list[str] | None = None) -> None:
        self._scripted = scripted or ["Hola, ¿en qué puedo ayudarte?"]
        self._index = 0
        self._history: list[IntelligenceRequest] = []

    async def health(self) -> bool:
        return True

    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        t0 = monotonic()
        self._history.append(request)

        if self._index < len(self._scripted):
            text = self._scripted[self._index]
            self._index += 1
        else:
            text = self._scripted[-1]

        latency = (monotonic() - t0) * 1000
        return IntelligenceResponse(
            raw_text=text,
            decision=IntelligenceDecision(
                decision_type=DecisionType.CONVERSATION,
                text_response=text,
                confidence=1.0,
            ),
            latency_ms=latency,
            model="fake",
        )

    def reset(self) -> None:
        self._index = 0
        self._history.clear()

    @property
    def requests(self) -> list[IntelligenceRequest]:
        return self._history
