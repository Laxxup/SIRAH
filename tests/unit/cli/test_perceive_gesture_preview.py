"""sirah-perceive gesture preview tests (M5.1): the reusable
perceive_gesture_preview() core over fakes needs no OpenCV, model,
mediapipe or hardware."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from sirah.behavior.attention import AttentionManager
from sirah.cli.perceive import perceive_gesture_preview
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.evidence import EvidenceHub
from sirah.perception.fanout import FrameBroker
from sirah.perception.gesture import (
    GestureDetection,
    HandGesture,
)
from sirah.perception.gesture_worker import GestureWorker


class FakeCamera:
    """Paces one frame per loop turn (a live capture source)."""

    def __init__(self, count: int) -> None:
        self._index = 0
        self._count = count
        self.stopped = False

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        if self._index >= self._count:
            return None
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame

    async def stop(self) -> None:
        self.stopped = True


class InfiniteCamera(FakeCamera):
    def __init__(self) -> None:
        super().__init__(0)

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame


class MultiFaceDetector:
    def __init__(self, targets: dict[int, list[GazeTarget]]) -> None:
        self._targets = targets

    def detect_many(self, frame: Frame) -> list[GazeTarget]:
        return self._targets.get(frame.index, [])


class FakeGestureRecognizer:
    def __init__(self, per_frame: list[list[HandGesture]]) -> None:
        self._per_frame = list(per_frame)
        self.closed = False
        self.calls = 0

    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        hands = self._per_frame[min(self.calls, len(self._per_frame) - 1)]
        self.calls += 1
        return GestureDetection(hands=tuple(hands), raw=(), timestamp_ms=self.calls)

    def close(self) -> None:
        self.closed = True


class SlowRecognizer(FakeGestureRecognizer):
    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        import time

        time.sleep(0.01)
        return super().recognize_detailed(frame)


class ExplodingRecognizer:
    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        raise RuntimeError("mediapipe crashed")

    def close(self) -> None:
        return None


def _advancing_clock() -> Callable[[], float]:
    state = {"t": -0.1}

    def clock() -> float:
        state["t"] += 0.1
        return state["t"]

    return clock


def _minimal_attention() -> AttentionManager:
    return AttentionManager(acquire_samples=1, loss_hold_samples=1, switch_samples=1)


def _thumb_up() -> HandGesture:
    return HandGesture("thumb_up", 0.93, "Right", 0)


def _wire_worker(source, recognizer, hub, clock) -> tuple[object, object, GestureWorker]:
    """Broker with one face subscriber and one gesture-worker subscriber,
    mirroring `_gesture_preview_entry`'s real wiring."""
    broker = FrameBroker(source)
    face_camera = broker.subscribe()
    gesture_camera = broker.subscribe()
    worker = GestureWorker(gesture_camera, recognizer, evidence=hub, clock=clock)
    return broker, face_camera, worker


async def test_gesture_preview_confirms_thumb_up_and_counts_metrics():
    source = FakeCamera(20)
    detector = MultiFaceDetector(
        {0: [GazeTarget(0.2, -0.3, 0.9)], 1: [GazeTarget(0.2, -0.3, 0.91)], 2: [], 3: []}
    )
    clock = _advancing_clock()
    hub = EvidenceHub(confirm_samples=1, release_window_s=0.1, cooldown_s=1.0)
    recognizer = FakeGestureRecognizer([[_thumb_up()]])
    broker, face_camera, worker = _wire_worker(source, recognizer, hub, clock)

    async with broker:
        summary = await perceive_gesture_preview(
            face_camera,
            detector,
            gesture_worker=worker,
            max_frames=4,
            interval_s=0.0,
            clock=clock,
            evidence=hub,
            attention=_minimal_attention(),
        )
    assert summary.frames == 4
    assert summary.faces == 2
    # exactly one confirm event, never one per frame
    assert summary.all_events.count("gesture_thumb_up_confirmed") == 1
    assert recognizer.closed
    assert source.stopped


async def test_gesture_preview_records_rejection_without_state():
    source = FakeCamera(2)
    detector = MultiFaceDetector({0: [], 1: []})
    clock = _advancing_clock()
    hub = EvidenceHub(min_confidence=0.6, confirm_samples=1)
    recognizer = FakeGestureRecognizer([[HandGesture("thumb_up", 0.3, "Right", 0)]] * 2)
    broker, face_camera, worker = _wire_worker(source, recognizer, hub, clock)

    async with broker:
        summary = await perceive_gesture_preview(
            face_camera,
            detector,
            gesture_worker=worker,
            max_frames=2,
            interval_s=0.0,
            clock=clock,
            evidence=hub,
            attention=_minimal_attention(),
        )
    assert summary.rejected_count >= 1
    assert summary.gesture_errors == 0
    assert hub.state_for("gesture", "Right") is None


async def test_gesture_preview_isolates_gesture_failure():
    source = FakeCamera(2)
    detector = MultiFaceDetector({0: [GazeTarget(0.0, 0.0, 0.9)], 1: []})
    clock = _advancing_clock()
    hub = EvidenceHub(confirm_samples=1)
    broker, face_camera, worker = _wire_worker(source, ExplodingRecognizer(), hub, clock)

    async with broker:
        summary = await perceive_gesture_preview(
            face_camera,
            detector,
            gesture_worker=worker,
            max_frames=2,
            interval_s=0.0,
            clock=clock,
            evidence=hub,
            attention=_minimal_attention(),
        )
    # the face path survived a MediaPipe failure
    assert summary.faces == 1
    assert summary.gesture_errors >= 1
    assert hub.state_for("person", "primary") is not None


async def test_gesture_preview_stops_worker_and_camera_on_cancellation():
    source = InfiniteCamera()
    detector = MultiFaceDetector({})
    clock = _advancing_clock()
    hub = EvidenceHub()
    recognizer = FakeGestureRecognizer([[]])
    broker, face_camera, worker = _wire_worker(source, recognizer, hub, clock)

    async with broker:
        task = asyncio.create_task(
            perceive_gesture_preview(
                face_camera,
                detector,
                gesture_worker=worker,
                max_frames=0,
                interval_s=0.0,
                clock=clock,
                evidence=hub,
                attention=_minimal_attention(),
            )
        )
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert recognizer.closed
    assert source.stopped


async def test_gesture_preview_slow_worker_never_delays_yunet():
    """A slow gesture worker must never delay YuNet and must receive a
    newer frame, not a stale queue (broker latest-frame semantics)."""
    source = FakeCamera(30)
    hub = EvidenceHub(confirm_samples=1)
    recognizer = SlowRecognizer([[]] * 30)
    broker, face_camera, worker = _wire_worker(source, recognizer, hub, clock=lambda: 0.0)

    async def face_loop(count: int) -> list[int]:
        indexes = []
        for _ in range(count):
            frame = await face_camera.next_frame()
            if frame is None:
                break
            indexes.append(frame.index)
        return indexes

    async with broker:
        await worker.start()
        face_frames = await face_loop(20)
        await asyncio.sleep(0.1)
        await worker.stop()

    assert face_frames == list(range(20))
    # slow gesture recognizer processed far fewer frames; YuNet saw all 20
    assert recognizer.calls < 20
    assert recognizer.calls >= 1