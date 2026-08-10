"""SerialTransport tests against the in-memory port double (Stage 5).

Covers: framing (trailing \\n, 64-byte line limit), partial reads across
multiple feeds, read timeouts, EOF -> LinkLost + degraded state,
reconnection through a fresh port via the queue factory, and the
single-authority rule (no open/auto-reopen by the adapter itself).
"""

from __future__ import annotations

import asyncio

import pytest

from sirah.hardware.serial_adapter import SerialTransport
from sirah.hardware.transport import (
    FramingError,
    LinkLost,
    ReadTimeout,
    TransportError,
    TransportState,
)
from tests.unit.hardware.memory_line_port import (
    BoundedFeed,
    MemoryLinePort,
    QueuePortFactory,
)

DEVICE = "/dev/ttyUSB0"


@pytest.mark.asyncio
async def test_connect_uses_factory_and_reports_connected() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(
        DEVICE,
        port_factory=lambda d, b: _noop_factory(port, d, b),
    )
    assert transport.status().state is TransportState.DISCONNECTED

    await transport.connect()
    assert transport.status().state is TransportState.CONNECTED
    assert transport.status().detail == ""


async def _noop_factory(port, device: str, baudrate: int) -> MemoryLinePort:
    assert device == DEVICE
    assert baudrate == 115200
    return port


@pytest.mark.asyncio
async def test_connect_is_idempotent() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()
    await transport.connect()  # second open is a no-op
    assert transport.status().state is TransportState.CONNECTED


@pytest.mark.asyncio
async def test_connect_failure_degrades() -> None:
    async def broken_factory(device: str, baudrate: int) -> MemoryLinePort:
        raise OSError("no such device")

    transport = SerialTransport(DEVICE, port_factory=broken_factory)
    with pytest.raises(TransportError):
        await transport.connect()
    assert transport.status().state is TransportState.DEGRADED
    assert "open failed" in transport.status().detail


@pytest.mark.asyncio
async def test_send_appends_newline() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    await transport.send(b"TARGET 0.5 -0.25")
    assert port.written() == b"TARGET 0.5 -0.25\n"


@pytest.mark.asyncio
async def test_send_overlong_line_is_framing_error() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    payload = b"X" * 64  # 64 + \n = 65 > 64
    with pytest.raises(FramingError):
        await transport.send(payload)


@pytest.mark.asyncio
async def test_send_while_disconnected_is_error() -> None:
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(MemoryLinePort(), d, b))
    with pytest.raises(TransportError):
        await transport.send(b"BLINK")


@pytest.mark.asyncio
async def test_read_returns_payload_without_newline() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    port.feed(b"OK\n")
    assert await transport.read() == b"OK"


@pytest.mark.asyncio
async def test_read_partial_feeds_assembles_line() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    feeder = BoundedFeed(port, chunk=3)
    task = asyncio.create_task(transport.read(timeout=5.0))
    await asyncio.sleep(0)
    assert not task.done()

    await feeder.feed_all(b"STATE 0.333 0.667 0\n")
    assert await task == b"STATE 0.333 0.667 0"


@pytest.mark.asyncio
async def test_read_timeout_raises_read_timeout() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(
        DEVICE,
        read_timeout_s=0.05,
        port_factory=lambda d, b: _noop_factory(port, d, b),
    )
    await transport.connect()

    with pytest.raises(ReadTimeout):
        await transport.read()


@pytest.mark.asyncio
async def test_read_overlong_line_is_framing_error() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    port.feed(b"X" * 65 + b"\n")
    with pytest.raises(FramingError):
        await transport.read()


@pytest.mark.asyncio
async def test_eof_raises_link_lost_and_degrades() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()

    port.set_eof()
    with pytest.raises(LinkLost):
        await transport.read()
    assert transport.status().state is TransportState.DEGRADED
    assert "link lost" in transport.status().detail


@pytest.mark.asyncio
async def test_reconnect_with_fresh_port() -> None:
    queue: asyncio.Queue[MemoryLinePort] = asyncio.Queue()
    port_a = MemoryLinePort()
    port_b = MemoryLinePort()
    queue.put_nowait(port_a)
    queue.put_nowait(port_b)

    transport = SerialTransport(DEVICE, port_factory=QueuePortFactory(queue))
    await transport.connect()
    assert transport._port is port_a

    port_a.set_eof()
    with pytest.raises(LinkLost):
        await transport.read()
    assert transport.status().state is TransportState.DEGRADED

    await transport.disconnect()
    assert transport.status().state is TransportState.DISCONNECTED

    await transport.connect()
    assert transport.status().state is TransportState.CONNECTED
    assert transport._port is port_b
    port_b.feed(b"READY 1\n")
    assert await transport.read() == b"READY 1"


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_and_returns_to_disconnected() -> None:
    port = MemoryLinePort()
    transport = SerialTransport(DEVICE, port_factory=lambda d, b: _noop_factory(port, d, b))
    await transport.connect()
    await transport.disconnect()
    await transport.disconnect()
    assert transport.status().state is TransportState.DISCONNECTED