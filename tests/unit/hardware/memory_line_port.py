"""In-memory LinePort double for SerialTransport tests (ADR-0010).

Simulates the real USB-UART byte stream without hardware: partial feeds,
scheduled EOF, write capture. Deliberately naive — one circular buffer,
asyncio primitives only.
"""

from __future__ import annotations

import asyncio


class MemoryLinePort:
    """Async byte stream double implementing the LinePort protocol."""

    def __init__(self) -> None:
        self._rx: bytearray = bytearray()
        self._tx: bytearray = bytearray()
        self._eof = False
        self._data_event = asyncio.Event()
        self._closed = False

    # --- feed side (test control) -------------------------------------

    def feed(self, chunk: bytes) -> None:
        self._rx.extend(chunk)
        self._data_event.set()

    def feed_str(self, s: str) -> None:
        self.feed(s.encode("ascii"))

    def set_eof(self) -> None:
        self._eof = True
        self._data_event.set()

    def written(self) -> bytes:
        return bytes(self._tx)

    # --- LinePort protocol ---------------------------------------------

    async def read_until(self, sep: bytes) -> bytes:
        while True:
            found = self._rx.find(sep)
            if found >= 0:
                line = bytes(self._rx[: found + len(sep)])
                del self._rx[: found + len(sep)]
                return line
            if self._eof:
                if self._rx:
                    line = bytes(self._rx)
                    self._rx.clear()
                    return line
                raise EOFError("memory port EOF")
            await self._data_event.wait()
            self._data_event.clear()

    async def write(self, data: bytes) -> None:
        self._tx.extend(data)

    async def close(self) -> None:
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed


async def port_factory_from_queue(
    queue: asyncio.Queue[MemoryLinePort],
) -> MemoryLinePort:
    """Factory adapter: yields ports from an asyncio.Queue for reconnect tests."""
    return await queue.get()


class QueuePortFactory:
    """Callable factory (device, baudrate) -> port from an asyncio.Queue."""

    def __init__(self, queue: asyncio.Queue[MemoryLinePort]) -> None:
        self._queue = queue

    async def __call__(self, device: str, baudrate: int) -> MemoryLinePort:
        return await self._queue.get()


class BoundedFeed:
    """Feeds a port in small chunks so partial reads are exercised."""

    def __init__(self, port: MemoryLinePort, chunk: int = 3) -> None:
        self._port = port
        self._chunk = chunk

    async def feed_all(self, data: bytes) -> None:
        for i in range(0, len(data), self._chunk):
            self._port.feed(data[i : i + self._chunk])
            await asyncio.sleep(0)