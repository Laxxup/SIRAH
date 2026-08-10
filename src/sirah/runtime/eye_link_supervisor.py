"""Single-reader supervisor for the PC-to-eyes serial link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sirah.hardware.transport import EyeTransport, ReadTimeout
from sirah.protocol.parse_line import parse_line


class EyeLinkSupervisor:
    """Poll STATUS and serialize command writes without owning transport lifecycle."""

    def __init__(
        self,
        transport: EyeTransport,
        *,
        heartbeat_cadence_s: float,
        read_timeout_s: float,
        liveness_timeout_s: float,
        on_link_lost: Callable[[Exception], None],
    ) -> None:
        if heartbeat_cadence_s <= 0:
            raise ValueError("heartbeat_cadence_s must be positive")
        if read_timeout_s <= 0:
            raise ValueError("read_timeout_s must be positive")
        if liveness_timeout_s <= 0:
            raise ValueError("liveness_timeout_s must be positive")
        self._transport = transport
        self._heartbeat_cadence_s = heartbeat_cadence_s
        self._read_timeout_s = read_timeout_s
        self._liveness_timeout_s = liveness_timeout_s
        self._on_link_lost = on_link_lost
        self._pending: asyncio.Queue[bytes] = asyncio.Queue()
        self._degraded = False
        self._last_state_at: float | None = None

    async def submit(self, payload: bytes) -> None:
        """Queue a payload for FIFO transmission during the next poll cycle."""
        await self._pending.put(payload)

    async def run(self, stop: asyncio.Event) -> None:
        """Run heartbeat/status polling until stopped or the link degrades."""
        loop = asyncio.get_running_loop()
        self._last_state_at = loop.time()
        try:
            while not stop.is_set():
                self._require_liveness(loop.time())
                await self._send_pending()
                await self._transport.send(b"HEARTBEAT")
                await self._transport.send(b"STATUS")
                await self._await_state(stop)
                wait_s = min(
                    self._heartbeat_cadence_s,
                    self._liveness_deadline() - loop.time(),
                )
                if wait_s <= 0:
                    self._require_liveness(loop.time())
                try:
                    await asyncio.wait_for(stop.wait(), timeout=wait_s)
                except TimeoutError:
                    continue
        except Exception as exc:  # noqa: BLE001 - any transport error degrades the link once.
            self._degrade(exc)

    async def _send_pending(self) -> None:
        while True:
            try:
                payload = self._pending.get_nowait()
            except asyncio.QueueEmpty:
                return
            await self._transport.send(payload)

    async def _await_state(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        read_deadline = loop.time() + self._read_timeout_s
        while not stop.is_set():
            self._require_liveness(loop.time())
            remaining = min(
                read_deadline - loop.time(),
                self._liveness_deadline() - loop.time(),
            )
            if remaining <= 0:
                raise ReadTimeout("no valid STATE received before timeout")
            payload = await self._read_or_stop(stop, remaining)
            if stop.is_set():
                return
            if loop.time() >= read_deadline or loop.time() >= self._liveness_deadline():
                raise ReadTimeout("no valid STATE received before timeout")
            if payload is None:
                raise ReadTimeout("no valid STATE received before timeout")
            result = parse_line(payload)
            if result.kind == "resp" and result.name == "STATE":
                self._last_state_at = loop.time()
                return

    async def _read_or_stop(self, stop: asyncio.Event, timeout: float) -> bytes | None:
        read_task = asyncio.create_task(self._transport.read(timeout=timeout))
        stop_task = asyncio.create_task(stop.wait())
        timeout_task = asyncio.create_task(asyncio.sleep(timeout))
        try:
            done, _ = await asyncio.wait(
                {read_task, stop_task, timeout_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                return None
            if timeout_task in done:
                raise ReadTimeout("no valid STATE received before timeout")
            return read_task.result()
        finally:
            for task in (read_task, stop_task, timeout_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(read_task, stop_task, timeout_task, return_exceptions=True)

    def _liveness_deadline(self) -> float:
        assert self._last_state_at is not None
        return self._last_state_at + self._liveness_timeout_s

    def _require_liveness(self, now: float) -> None:
        if now >= self._liveness_deadline():
            raise ReadTimeout("no valid STATE received within liveness timeout")

    def _degrade(self, error: Exception) -> None:
        if self._degraded:
            return
        self._degraded = True
        self._on_link_lost(error)
