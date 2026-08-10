"""SerialTransport — pyserial-asyncio adapter (Stage 5).

Framing per spec 4: payload <= 63 bytes, full line <= 64 bytes including
the terminating "\\n", 115200 8N1. Long lines are a FramingError, not
silently truncated.

Testability: the low-level port is injectable (port_factory). Tests pass
an in-memory double (partial feeds, EOF, reconnection) so no serial
hardware is needed; the default factory opens the real USB-UART.

Single-authority rule: this adapter NEVER opens the port on its own, never
auto-reconnects and never retries; connect()/disconnect() are called by
the runtime only (Stage 5/7).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import serial_asyncio

from sirah.hardware.transport import (
    EyeTransport,
    FramingError,
    LinkLost,
    ReadTimeout,
    TransportError,
    TransportState,
    TransportStatus,
)

_logger = logging.getLogger(__name__)

# spec 4: max line length 64 bytes INCLUDING the terminating \n
MAX_LINE_BYTES = 64
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_S = 1.0


class LinePort(Protocol):
    """Minimal async byte-line port the adapter needs (testable double)."""

    async def read_until(self, sep: bytes) -> bytes:
        """Read until sep (included). EOF -> raises EOFError."""

    async def write(self, data: bytes) -> None:
        ...

    async def close(self) -> None:
        ...


async def _default_port_factory(device: str, baudrate: int) -> LinePort:
    reader, writer = await serial_asyncio.open_serial_connection(
        url=device, baudrate=baudrate
    )
    return _PyserialLinePort(reader, writer)


class _PyserialLinePort:
    """Adapter around pyserial-asyncio (reader, writer)."""

    def __init__(self, reader, writer) -> None:
        self._reader = reader
        self._writer = writer

    async def read_until(self, sep: bytes) -> bytes:
        try:
            return await self._reader.readuntil(sep)
        except asyncio.IncompleteReadError as exc:
            raise EOFError("serial EOF") from exc

    async def write(self, data: bytes) -> None:
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception as exc:  # noqa: BLE001 - best-effort teardown
            _logger.debug("serial close ignored: %r", exc)


class SerialTransport(EyeTransport):
    """USB-UART transport for the ESP32 link (one line per send/read)."""

    def __init__(
        self,
        device: str,
        baudrate: int = DEFAULT_BAUDRATE,
        *,
        read_timeout_s: float = DEFAULT_TIMEOUT_S,
        port_factory: (
            Callable[[str, int], Awaitable[LinePort]] | None
        ) = None,
    ) -> None:
        self._device = device
        self._baudrate = baudrate
        self._read_timeout_s = read_timeout_s
        self._port_factory = port_factory or _default_port_factory
        self._port: LinePort | None = None
        self._status = TransportStatus(TransportState.DISCONNECTED)

    # --- lifecycle (runtime-owned; single authority) --------------------

    async def connect(self) -> None:
        if self._status.state is TransportState.CONNECTED:
            return
        if self._status.state is TransportState.CONNECTING:
            raise TransportError("connect already in progress")
        self._status = TransportStatus(TransportState.CONNECTING)
        try:
            self._port = await self._port_factory(self._device, self._baudrate)
        except Exception as exc:
            self._port = None
            self._status = TransportStatus(
                TransportState.DEGRADED, detail=f"open failed: {exc!r}"
            )
            raise TransportError(f"open {self._device}: {exc!r}") from exc
        self._status = TransportStatus(TransportState.CONNECTED)

    async def disconnect(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            try:
                await port.close()
            except Exception as exc:  # noqa: BLE001 - best-effort teardown
                _logger.debug("disconnect close ignored: %r", exc)
        self._status = TransportStatus(TransportState.DISCONNECTED)

    # --- wire operations ----------------------------------------------

    async def send(self, payload: bytes) -> None:
        line = payload + b"\n"
        if len(line) > MAX_LINE_BYTES:
            raise FramingError(
                f"line {len(line)} bytes > {MAX_LINE_BYTES} (spec 4)"
            )
        port = self._require_port()
        try:
            await port.write(line)
        except TransportError:
            raise
        except Exception as exc:  # noqa: BLE001 - link loss surfaces as LinkLost
            await self._lose(exc)

    async def read(self, timeout: float | None = None) -> bytes | None:
        port = self._require_port()
        seconds = self._read_timeout_s if timeout is None else timeout
        try:
            line = await asyncio.wait_for(port.read_until(b"\n"), timeout=seconds)
        except TimeoutError:
            raise ReadTimeout(f"no line within {seconds}s") from None
        except EOFError as exc:
            await self._lose(exc)
            return None  # unreachable: _lose raises LinkLost
        if len(line) > MAX_LINE_BYTES:
            raise FramingError(f"line {len(line)} bytes > {MAX_LINE_BYTES}")
        return line.removesuffix(b"\n")

    def status(self) -> TransportStatus:
        return self._status

    # --- internals -----------------------------------------------------

    def _require_port(self) -> LinePort:
        if self._status.state is not TransportState.CONNECTED or (
            self._port is None
        ):
            raise TransportError(
                f"not connected (state={self._status.state.value})"
            )
        return self._port

    async def _lose(self, exc: Exception) -> None:
        self._port = None
        self._status = TransportStatus(
            TransportState.DEGRADED, detail=f"link lost: {exc!r}"
        )
        raise LinkLost(f"link lost on {self._device}: {exc!r}") from exc