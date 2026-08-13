"""Human-readable latency markers for live conversation diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from time import monotonic


class TurnTiming:
    """Print elapsed stage and turn durations without retaining conversation content."""

    def __init__(
        self,
        *,
        write: Callable[[str], None] = print,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._write = write
        self._monotonic_clock = monotonic_clock
        self._wall_clock = wall_clock
        self._started_at: float | None = None
        self._last_at: float | None = None

    def mark(self, label: str) -> None:
        now = self._monotonic_clock()
        timestamp = self._wall_clock().strftime("%H:%M:%S.%f")[:-3]
        if self._started_at is None:
            self._started_at = now
            self._last_at = now
            self._write(f"[{timestamp}] {label}")
            return
        if self._last_at is None:
            raise RuntimeError("turn timing is missing its previous stage")
        stage_ms = round((now - self._last_at) * 1000)
        turn_ms = round((now - self._started_at) * 1000)
        self._last_at = now
        self._write(f"[{timestamp}] {label} | etapa {stage_ms} ms | turno {turn_ms} ms")

    def reset(self) -> None:
        self._started_at = None
        self._last_at = None
