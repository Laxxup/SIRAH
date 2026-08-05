"""IntelligencePort — async protocol for conversational reasoning."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from sirah.types import IntelligenceRequest, IntelligenceResponse

__all__ = ["IntelligencePort"]


@runtime_checkable
class IntelligencePort(Protocol):
    async def decide(self, request: IntelligenceRequest) -> IntelligenceResponse: ...

    async def health(self) -> bool: ...
