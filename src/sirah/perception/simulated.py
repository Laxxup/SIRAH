"""Simulated perception — deterministic doubles for testing."""

from __future__ import annotations

from time import monotonic

from sirah.errors import PerceptionUnavailableError
from sirah.types import FaceDetection, PerceptionFrame

__all__ = ["SimulatedPerception"]


class SimulatedPerception:
    def __init__(
        self,
        scripted_faces: list[tuple[FaceDetection, ...]] | None = None,
        fail_after: int | None = None,
    ) -> None:
        self._scripted = scripted_faces or []
        self._index = 0
        self._fail_after = fail_after
        self._call_count = 0
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def health(self) -> bool:
        return self._running

    async def capture(self) -> PerceptionFrame:
        if not self._running:
            raise PerceptionUnavailableError("not started")

        self._call_count += 1

        if self._fail_after is not None and self._call_count > self._fail_after:
            raise PerceptionUnavailableError("simulated failure")

        faces = ()
        if self._scripted:
            faces = self._scripted[min(self._index, len(self._scripted) - 1)]
            self._index += 1

        return PerceptionFrame(timestamp=monotonic(), faces=faces)

    def reset(self) -> None:
        self._index = 0
        self._call_count = 0
