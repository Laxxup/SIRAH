"""HeartbeatWriter tests (Stage 7, semantics of Stage 11)."""

from __future__ import annotations

import asyncio

import pytest

from sirah.runtime.heartbeat import HeartbeatWriter


class RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.fail = False

    async def send(self, payload: bytes) -> None:
        if self.fail:
            raise RuntimeError("link lost")
        self.sent.append(payload)


async def test_sends_heartbeat_until_stop():
    transport = RecordingTransport()
    stop = asyncio.Event()
    task = asyncio.create_task(
        HeartbeatWriter(transport, cadence_s=0.02).run(stop)
    )
    await asyncio.sleep(0.07)
    stop.set()
    await task
    assert transport.sent == [b"HEARTBEAT"] * 4  # t=0.02..0.08 + final tick


async def test_silently_returns_on_transport_failure():
    transport = RecordingTransport()
    transport.fail = True
    task = asyncio.create_task(
        HeartbeatWriter(transport, cadence_s=0.01).run(asyncio.Event())
    )
    await asyncio.wait_for(task, timeout=1.0)


async def test_notifies_failure_once():
    transport = RecordingTransport()
    transport.fail = True
    errors: list[Exception] = []
    await HeartbeatWriter(transport, cadence_s=0.01, on_failure=errors.append).run(
        asyncio.Event()
    )
    assert len(errors) == 1
    assert str(errors[0]) == "link lost"


@pytest.mark.asyncio
async def test_zero_cadence_guard_is_bounded():
    transport = RecordingTransport()
    stop = asyncio.Event()
    task = asyncio.create_task(
        HeartbeatWriter(transport, cadence_s=0.001).run(stop)
    )
    await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
