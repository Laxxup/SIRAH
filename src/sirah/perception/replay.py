"""Deterministic in-memory camera source for offline replay."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from sirah.perception.contracts import Frame


class ReplayCameraSource:
    """Expose a finite payload sequence through the CameraSource contract."""

    def __init__(self, payloads: Iterable[object]) -> None:
        self._payloads: Iterator[object] = iter(payloads)
        self._index = 0
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def next_frame(self) -> Frame | None:
        if not self._running:
            return None
        try:
            payload = next(self._payloads)
        except StopIteration:
            return None
        frame = Frame(index=self._index, payload=payload)
        self._index += 1
        return frame

    async def stop(self) -> None:
        self._running = False
