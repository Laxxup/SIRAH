"""Doble guionizado de IntelligencePort para pruebas y ejemplos offline."""

from collections.abc import Iterable

from .intelligence import (
    IntelligenceRequest,
    IntelligenceResponse,
)


class FakeIntelligenceAdapter:
    """Devuelve respuestas predefinidas sin red."""

    def __init__(self, responses: Iterable[IntelligenceResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[IntelligenceRequest] = []

    def decide(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self.requests.append(request)
        try:
            return next(self._responses)
        except StopIteration as error:
            raise RuntimeError("El guion de inteligencia se agotó.") from error

