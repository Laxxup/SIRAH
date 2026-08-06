"""PerceptionPort — async protocol for visual sensing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sirah.types import PerceptionFrame

__all__ = ["PerceptionPort"]


@runtime_checkable
class PerceptionPort(Protocol):
    async def capture(self) -> PerceptionFrame: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def health(self) -> bool: ...
