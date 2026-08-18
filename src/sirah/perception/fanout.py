"""Shared frame broker: ONE camera owner, many latest-frame consumers.

Foundation for telepresence / multi-consumer perception. SIRAH must never
evolve into "sirah-runtime opens /dev/video0 + sirah-perceive opens
/dev/video0 + WebRTC opens /dev/video0". A `FrameBroker` owns the single
physical `CameraSource`; every consumer (YuNet, MediaPipe, the future
WebRTC encoder input, VLM snapshots) is a *subscriber* that implements
the same `CameraSource` contract, so existing perception code works
unchanged.

Freshness is non-negotiable: each subscriber keeps exactly one latest
frame slot. A slow consumer skips (drops) intermediate frames instead of
queuing them, so a slow WebRTC/MediaPipe/YOLO consumer never delays
another and no growing backlog forms. The broker is opt-in — a source
consumed directly still works exactly as before.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Self

from sirah.perception.contracts import CameraSource, Frame


@dataclass
class _Slot:
    """One subscriber's latest-frame slot (never a queue)."""

    frame: Frame | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    ended: bool = False


class FrameSubscriber:
    """A `CameraSource`-shaped view of the broker for one consumer.

    `next_frame()` waits for the newest frame the broker has produced and
    returns it, or returns `None` once the broker has stopped/ended —
    identical semantics to any other `CameraSource`. Frames that arrive
    while the consumer is busy are overwritten in its slot and never
    delivered (latest-frame semantics).
    """

    def __init__(self, slot: _Slot) -> None:
        self._slot = slot

    async def start(self) -> None:
        # lifecycle belongs to the broker, not the subscriber
        return None

    async def next_frame(self) -> Frame | None:
        slot = self._slot
        while True:
            if slot.ended and slot.frame is None:
                return None
            await slot.event.wait()
            slot.event.clear()
            if slot.ended and slot.frame is None:
                return None
            frame = slot.frame
            if frame is not None:
                # delivered once: a consumer that has not yet read the
                # latest frame still sees it before the end-of-stream
                slot.frame = None
                return frame

    async def stop(self) -> None:
        # lifecycle belongs to the broker, not the subscriber
        return None


class FrameBroker:
    """Owns one camera and fans its latest frame out to subscribers.

    Usage::

        broker = FrameBroker(OpenCVCameraSource(device))
        camera = broker.subscribe()   # a CameraSource, drop-in for perception
        await broker.start()
        ...
        await broker.stop()
    """

    def __init__(self, source: CameraSource) -> None:
        self._source = source
        self._subscribers: list[FrameSubscriber] = []
        self._task: asyncio.Task[None] | None = None

    @property
    def source(self) -> CameraSource:
        """The single physical camera this broker owns."""
        return self._source

    @property
    def source_stats(self):
        """Underlying camera freshness stats, when the source exposes them."""
        stats = getattr(self._source, "stats", None)
        return stats() if callable(stats) else None

    def subscribe(self) -> FrameSubscriber:
        """Register a new latest-frame consumer (allowed before start)."""
        subscriber = FrameSubscriber(_Slot())
        self._subscribers.append(subscriber)
        return subscriber

    async def start(self) -> None:
        """Open the source exactly once and start pumping frames."""
        if self._task is not None:
            return
        await self._source.start()
        for subscriber in self._subscribers:
            subscriber._slot.ended = False
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            while True:
                frame = await self._source.next_frame()
                if frame is None:
                    return
                self._broadcast(frame)
        finally:
            for subscriber in self._subscribers:
                subscriber._slot.ended = True
                subscriber._slot.event.set()

    def _broadcast(self, frame: Frame) -> None:
        for subscriber in self._subscribers:
            subscriber._slot.frame = frame
            subscriber._slot.event.set()

    async def stop(self) -> None:
        """Close the source once and wake every waiting subscriber."""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._source.stop()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()