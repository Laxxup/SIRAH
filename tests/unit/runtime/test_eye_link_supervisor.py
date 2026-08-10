from __future__ import annotations

import asyncio
from collections import deque

from sirah.hardware.transport import LinkLost, ReadTimeout
from sirah.runtime.eye_link_supervisor import EyeLinkSupervisor


class ScriptedTransport:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.operations: list[bytes] = []
        self.replies: deque[bytes | Exception | None] = deque()

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)
        self.operations.append(b"send:" + payload)
        if payload.startswith(b"TARGET"):
            self.replies.append(b"OK")
        elif payload == b"STATUS":
            self.replies.append(b"STATE 0 0 0")

    async def read(self, timeout: float | None = None) -> bytes | None:
        self.operations.append(b"read")
        if self.replies:
            reply = self.replies.popleft()
            if isinstance(reply, Exception):
                raise reply
            return reply
        return None


async def _wait_for(predicate, timeout: float = 0.2) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not met")


async def test_status_state_keeps_supervisor_running():
    transport = ScriptedTransport()
    failures: list[Exception] = []
    stop = asyncio.Event()
    task = asyncio.create_task(
        EyeLinkSupervisor(
            transport,  # type: ignore[arg-type]
            heartbeat_cadence_s=0.01,
            read_timeout_s=0.01,
            liveness_timeout_s=1.0,
            on_link_lost=failures.append,
        ).run(stop)
    )

    await _wait_for(lambda: b"STATE 0 0 0" not in transport.sent and b"STATUS" in transport.sent)
    stop.set()
    await task

    assert failures == []
    assert transport.sent[:2] == [b"HEARTBEAT", b"STATUS"]


async def test_target_ok_before_state_does_not_break_status_polling():
    transport = ScriptedTransport()
    failures: list[Exception] = []
    stop = asyncio.Event()
    supervisor = EyeLinkSupervisor(
        transport,  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.01,
        liveness_timeout_s=1.0,
        on_link_lost=failures.append,
    )
    await supervisor.submit(b"TARGET 0.5 0")
    task = asyncio.create_task(supervisor.run(stop))

    await _wait_for(lambda: b"STATUS" in transport.sent)
    stop.set()
    await task

    assert failures == []
    assert transport.sent[:3] == [b"TARGET 0.5 0", b"HEARTBEAT", b"STATUS"]
    assert transport.operations[:4] == [
        b"send:TARGET 0.5 0",
        b"send:HEARTBEAT",
        b"send:STATUS",
        b"read",
    ]


async def test_submitted_commands_are_sent_fifo_before_the_poll():
    transport = ScriptedTransport()
    failures: list[Exception] = []
    stop = asyncio.Event()
    supervisor = EyeLinkSupervisor(
        transport,  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.01,
        liveness_timeout_s=1.0,
        on_link_lost=failures.append,
    )
    await supervisor.submit(b"TARGET 0.5 0")
    await supervisor.submit(b"CENTER")
    task = asyncio.create_task(supervisor.run(stop))

    await _wait_for(lambda: b"STATUS" in transport.sent)
    stop.set()
    await task

    assert failures == []
    assert transport.sent[:4] == [b"TARGET 0.5 0", b"CENTER", b"HEARTBEAT", b"STATUS"]


async def test_err_and_ok_before_state_do_not_break_status_polling():
    transport = ScriptedTransport()
    transport.replies.append(b"ERR 1")
    failures: list[Exception] = []
    stop = asyncio.Event()
    task = asyncio.create_task(
        EyeLinkSupervisor(
            transport,  # type: ignore[arg-type]
            heartbeat_cadence_s=0.01,
            read_timeout_s=0.01,
            liveness_timeout_s=1.0,
            on_link_lost=failures.append,
        ).run(stop)
    )

    await _wait_for(lambda: transport.operations.count(b"read") >= 2)
    stop.set()
    await task

    assert failures == []


async def test_timeout_degrades_once():
    transport = ScriptedTransport()
    transport.replies.append(None)
    failures: list[Exception] = []

    await EyeLinkSupervisor(
        transport,  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.01,
        liveness_timeout_s=1.0,
        on_link_lost=failures.append,
    ).run(asyncio.Event())

    assert len(failures) == 1
    assert isinstance(failures[0], ReadTimeout)


async def test_link_lost_degrades_once():
    transport = ScriptedTransport()
    transport.replies.append(LinkLost("unplugged"))
    failures: list[Exception] = []

    await EyeLinkSupervisor(
        transport,  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.01,
        liveness_timeout_s=1.0,
        on_link_lost=failures.append,
    ).run(asyncio.Event())

    assert len(failures) == 1
    assert isinstance(failures[0], LinkLost)


async def test_send_failure_degrades_once():
    class FailingSendTransport(ScriptedTransport):
        async def send(self, payload: bytes) -> None:
            raise LinkLost("unplugged")

    failures: list[Exception] = []
    await EyeLinkSupervisor(
        FailingSendTransport(),  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.01,
        liveness_timeout_s=1.0,
        on_link_lost=failures.append,
    ).run(asyncio.Event())

    assert len(failures) == 1
    assert isinstance(failures[0], LinkLost)


async def test_heartbeat_is_sent_each_cycle():
    transport = ScriptedTransport()
    failures: list[Exception] = []
    stop = asyncio.Event()
    task = asyncio.create_task(
        EyeLinkSupervisor(
            transport,  # type: ignore[arg-type]
            heartbeat_cadence_s=0.005,
            read_timeout_s=0.01,
            liveness_timeout_s=1.0,
            on_link_lost=failures.append,
        ).run(stop)
    )

    await _wait_for(lambda: transport.sent.count(b"HEARTBEAT") >= 2)
    stop.set()
    await task

    assert failures == []


async def test_liveness_timeout_degrades_when_only_ok_arrives():
    class OkOnlyTransport(ScriptedTransport):
        async def read(self, timeout: float | None = None) -> bytes | None:
            await asyncio.sleep(0.002)
            return b"OK"

    failures: list[Exception] = []
    await EyeLinkSupervisor(
        OkOnlyTransport(),  # type: ignore[arg-type]
        heartbeat_cadence_s=0.01,
        read_timeout_s=0.1,
        liveness_timeout_s=0.01,
        on_link_lost=failures.append,
    ).run(asyncio.Event())

    assert len(failures) == 1
    assert isinstance(failures[0], ReadTimeout)


async def test_liveness_timeout_interrupts_a_long_cadence_wait():
    transport = ScriptedTransport()
    failures: list[Exception] = []

    await asyncio.wait_for(
        EyeLinkSupervisor(
            transport,  # type: ignore[arg-type]
            heartbeat_cadence_s=0.1,
            read_timeout_s=0.1,
            liveness_timeout_s=0.01,
            on_link_lost=failures.append,
        ).run(asyncio.Event()),
        timeout=0.05,
    )

    assert len(failures) == 1
    assert isinstance(failures[0], ReadTimeout)


async def test_stop_interrupts_an_outstanding_read():
    class BlockingReadTransport(ScriptedTransport):
        def __init__(self) -> None:
            super().__init__()
            self.read_started = asyncio.Event()

        async def read(self, timeout: float | None = None) -> bytes | None:
            self.read_started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    transport = BlockingReadTransport()
    failures: list[Exception] = []
    stop = asyncio.Event()
    task = asyncio.create_task(
        EyeLinkSupervisor(
            transport,  # type: ignore[arg-type]
            heartbeat_cadence_s=0.1,
            read_timeout_s=1.0,
            liveness_timeout_s=1.0,
            on_link_lost=failures.append,
        ).run(stop)
    )

    await transport.read_started.wait()
    stop.set()
    await asyncio.wait_for(task, timeout=0.05)

    assert failures == []
