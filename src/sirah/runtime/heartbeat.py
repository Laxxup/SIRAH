"""Heartbeat writer task (Stage 11 semantics, scaffolded in Stage 7).

While the eyes subsystem is ready/armed, the runtime sends a HEARTBEAT
verb at `cadence_s` (proposed 1 s, Plan A2). The firmware watchdog
(Stage 11) counts down from the last received heartbeat and eases the gaze
back to CENTER on timeout (3 s proposed).

This task owns sending only; the LinkLost/degraded consequence is
reported to the registry so the app keeps running (Stage 7 rule).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable


class HeartbeatWriter:
    """Periodic HEARTBEAT sender, sibling of the app's main loop."""

    def __init__(
        self,
        transport,
        cadence_s: float = 1.0,
        on_failure: Callable[[Exception], None] | None = None,
    ) -> None:
        self._transport = transport
        self._cadence_s = cadence_s
        self._on_failure = on_failure

    async def run(self, stop: asyncio.Event) -> None:
        """Send HEARTBEAT every cadence until the stop event is set.

        Stops silently on any transport failure (the registry level is the
        report channel; caller decides degradation).
        """
        while not stop.is_set():
            try:
                await self._transport.send(b"HEARTBEAT")
            except Exception as exc:  # noqa: BLE001 - link loss stops the writer
                if self._on_failure is not None:
                    self._on_failure(exc)
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._cadence_s)
            except TimeoutError:
                continue
