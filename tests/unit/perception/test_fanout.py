"""Shared frame broker (fan-out) tests: single camera owner, latest-frame
subscribers, no unbounded queues, clean lifecycle over fakes."""

from __future__ import annotations

import asyncio

from sirah.perception.contracts import Frame
from sirah.perception.fanout import FrameBroker


class FakeCamera:
    """Paces one frame per loop turn, like a real capture device."""

    def __init__(self, frames: list[int]) -> None:
        self._frames = iter(frames)
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        try:
            index = next(self._frames)
        except StopIteration:
            return None
        return Frame(index=index, payload=None, captured_at=float(index))

    async def stop(self) -> None:
        self.stops += 1


class BlockingCamera(FakeCamera):
    def __init__(self, frames: list[int], release: asyncio.Event) -> None:
        super().__init__(frames)
        self._release = release

    async def next_frame(self) -> Frame | None:
        await self._release.wait()
        return await super().next_frame()


class InfiniteCamera(FakeCamera):
    """A live camera that never ends (like /dev/video0)."""

    def __init__(self) -> None:
        super().__init__([])
        self._index = 0

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame


async def collect(camera, count: int) -> list[int]:
    """Sequentially read `count` frames from one subscriber (realistic)."""
    indexes = []
    for _ in range(count):
        indexes.append((await camera.next_frame()).index)
    return indexes


async def test_broker_fans_out_same_frames_to_all_subscribers():
    source = FakeCamera(list(range(6)))
    broker = FrameBroker(source)
    left, right = broker.subscribe(), broker.subscribe()
    await broker.start()

    left_frames, right_frames = await asyncio.gather(
        collect(left, 6), collect(right, 6)
    )
    assert left_frames == list(range(6))
    assert right_frames == list(range(6))
    await broker.stop()
    assert source.starts == 1
    assert source.stops == 1


async def test_broker_opens_camera_exactly_once_for_many_subscribers():
    source = FakeCamera(list(range(10)))
    broker = FrameBroker(source)
    _ = [broker.subscribe() for _ in range(5)]
    await broker.start()
    await broker.stop()
    assert source.starts == 1
    assert source.stops == 1


async def test_idle_subscriber_skips_stale_frames_gets_latest():
    source = FakeCamera(list(range(100)))
    broker = FrameBroker(source)
    fast, slow = broker.subscribe(), broker.subscribe()
    await broker.start()

    # the fast consumer reads 20 frames while the slow one is idle
    await collect(fast, 20)
    # the slow consumer must receive a fresh frame, never the stale first one
    frame = await slow.next_frame()
    assert frame.index >= 19
    assert frame.index != 0
    await broker.stop()


async def test_subscriber_never_builds_a_backlog_while_busy():
    source = InfiniteCamera()
    broker = FrameBroker(source)
    subscriber = broker.subscribe()
    await broker.start()

    assert await collect(subscriber, 3) == [0, 1, 2]
    # while the consumer is busy, the pump advances to the tail
    await asyncio.sleep(0.05)
    # a single poll yields ONE fresh frame, never an accumulated queue
    frame = await subscriber.next_frame()
    assert frame.index >= 20
    assert (await subscriber.next_frame()).index > frame.index
    await broker.stop()


async def test_end_of_stream_propagates_to_all_subscribers():
    source = FakeCamera([1, 2, 3])
    broker = FrameBroker(source)
    left, right = broker.subscribe(), broker.subscribe()
    await broker.start()

    seen_left, seen_right = await asyncio.gather(
        collect(left, 3), collect(right, 3)
    )
    assert seen_left == [1, 2, 3]
    assert seen_right == [1, 2, 3]
    assert (await left.next_frame()) is None
    assert (await right.next_frame()) is None
    await broker.stop()


async def test_stop_wakes_waiting_subscribers_with_eof():
    release = asyncio.Event()
    source = BlockingCamera(list(range(3)), release)
    broker = FrameBroker(source)
    subscriber = broker.subscribe()
    await broker.start()

    waiting = asyncio.create_task(subscriber.next_frame())
    await asyncio.sleep(0.01)
    assert not waiting.done()
    await broker.stop()
    assert await waiting is None


async def test_pump_cancellation_stops_source():
    release = asyncio.Event()
    source = BlockingCamera(list(range(3)), release)
    broker = FrameBroker(source)
    await broker.start()
    await broker.stop()
    await asyncio.sleep(0.01)
    assert source.stops == 1


async def test_broker_as_async_context_manager():
    source = FakeCamera(list(range(2)))
    async with FrameBroker(source) as broker:
        assert (await broker.subscribe().next_frame()).index == 0
    assert source.stops == 1


async def test_subscriber_is_a_drop_in_camera_source():
    source = FakeCamera(list(range(2)))
    broker = FrameBroker(source)
    subscriber = broker.subscribe()

    async def consume(camera) -> list[int]:
        indexes = []
        while True:
            frame = await camera.next_frame()
            if frame is None:
                break
            indexes.append(frame.index)
        return indexes

    task = asyncio.create_task(consume(subscriber))
    await broker.start()
    assert await task == [0, 1]
    await broker.stop()