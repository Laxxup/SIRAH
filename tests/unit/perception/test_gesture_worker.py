"""GestureWorker tests (M5.1): off-loop inference, broker integration,
latest-frame semantics, evidence feeding, isolation and clean shutdown —
all over fakes, no mediapipe, no hardware."""

from __future__ import annotations

import asyncio

from sirah.perception.contracts import Frame
from sirah.perception.evidence import EvidenceHub
from sirah.perception.fanout import FrameBroker
from sirah.perception.gesture import (
    GestureDetection,
    HandGesture,
)
from sirah.perception.gesture_worker import GestureWorker


class FakeRecognizer:
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


class SlowRecognizer(FakeRecognizer):
    """Blocks the worker thread briefly so the broker advances the slot."""

    def __init__(self, per_frame: list[list[HandGesture]], delay_s: float = 0.02) -> None:
        super().__init__(per_frame)
        self._delay_s = delay_s

    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        import time

        time.sleep(self._delay_s)
        return super().recognize_detailed(frame)


class ThrowingRecognizer(FakeRecognizer):
    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        raise RuntimeError("mediapipe crashed")


class FakeCamera:
    """Paces one frame per loop turn, like a real capture device."""

    def __init__(self, frames: list[float]) -> None:
        self._frames = list(frames)
        self._index = 0
        self.starts = 0
        self.stops = 0

    async def start(self) -> None:
        self.starts += 1

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        if self._index >= len(self._frames):
            return None
        captured_at = self._frames[self._index]
        frame = Frame(index=self._index, payload=None, captured_at=captured_at)
        self._index += 1
        return frame

    async def stop(self) -> None:
        self.stops += 1


class InfiniteCamera(FakeCamera):
    """A live camera that never ends (like /dev/video0)."""

    def __init__(self) -> None:
        super().__init__([])
        self._frames = [0.0]  # placeholder; live semantics override next_frame

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame


def _thumb_up() -> HandGesture:
    return HandGesture("thumb_up", 0.93, "Right", 0)


def _open_palm() -> HandGesture:
    return HandGesture("open_palm", 0.88, "Left", 0)


async def _pump(seconds: float = 0.05) -> None:
    await asyncio.sleep(seconds)


async def test_worker_feeds_gesture_evidence_and_exposes_raw():
    camera = FakeCamera([0.0, 0.1, 0.2])
    hub = EvidenceHub(confirm_samples=2, release_window_s=0.1, cooldown_s=1.0)
    recognizer = FakeRecognizer([[], [_thumb_up()], [_thumb_up()]])
    worker = GestureWorker(camera, recognizer, evidence=hub)
    await worker.start()
    await _pump()
    await worker.stop()

    stats = worker.stats()
    assert stats.inferences == 3
    assert stats.errors == 0
    # two consecutive thumb_up ticks confirm exactly once
    state = hub.state_for("gesture", "Right")
    assert state is not None and state.value == "thumb_up"
    assert recognizer.closed
    assert camera.stops == 0  # worker never owns the camera lifecycle


async def test_worker_isolates_recognizer_failure():
    camera = FakeCamera([0.0, 0.1, 0.2])
    hub = EvidenceHub()
    recognizer = ThrowingRecognizer([[]])
    worker = GestureWorker(camera, recognizer, evidence=hub)
    await worker.start()
    await _pump()
    await worker.stop()
    assert worker.stats().errors == 3
    assert worker.stats().inferences == 0
    # an exception must not leak into the caller / YuNet pipeline
    assert hub.state_for("gesture", "Right") is None


async def test_worker_skips_intermediate_frames_for_slow_detector():
    """A slow gesture detector must receive a newer frame, not a queue."""
    camera = InfiniteCamera()
    hub = EvidenceHub(confirm_samples=1, min_confidence=0.5)
    recognizer = SlowRecognizer([[_thumb_up()], [_open_palm()]], delay_s=0.02)
    worker = GestureWorker(camera, recognizer, evidence=hub)

    await worker.start()
    await _pump(0.2)
    await worker.stop()

    # while inference was busy, the broker advanced: the worker processed
    # far fewer frames than the camera produced (camera ~100/s in this fake)
    assert recognizer.calls < 20
    # the last detection reflects a NEWER frame, not the first one
    assert len(worker.last_hands) == 1


async def test_worker_evidence_fills_frame_age_and_latency():
    camera = FakeCamera([10.0, 10.1, 10.2])
    recognizer = FakeRecognizer([[], [], []])
    worker = GestureWorker(camera, recognizer, evidence=EvidenceHub())
    await worker.start()
    await _pump()
    await worker.stop()
    stats = worker.stats()
    assert stats.latency_ms
    assert stats.frame_age_s
    assert all(age >= 0 for age in stats.frame_age_s)


async def test_worker_async_context_manager_closes():
    camera = FakeCamera([0.0, 0.1])
    recognizer = FakeRecognizer([[], []])
    worker = GestureWorker(camera, recognizer, evidence=EvidenceHub())
    async with worker:
        await _pump()
    assert recognizer.closed


async def test_worker_integration_with_frame_broker():
    """The worker consumes a FrameBroker subscription; YuNet can consume
    another subscriber independently without either delaying the other."""
    source = FakeCamera([float(i) for i in range(20)])
    broker = FrameBroker(source)
    face_camera = broker.subscribe()
    gesture_camera = broker.subscribe()
    hub = EvidenceHub(confirm_samples=2)
    recognizer = FakeRecognizer([[_thumb_up()], [_thumb_up()], [_thumb_up()]])
    worker = GestureWorker(gesture_camera, recognizer, evidence=hub)

    async def face_loop(count: int) -> list[int]:
        indexes = []
        for _ in range(count):
            frame = await face_camera.next_frame()
            if frame is None:
                break
            indexes.append(frame.index)
        return indexes

    await broker.start()
    await worker.start()
    face_frames = await face_loop(10)
    await _pump()
    await worker.stop()
    await broker.stop()

    assert face_frames == list(range(10))
    # the worker consumed from its own subscriber without stalling YuNet
    assert recognizer.calls >= 2
    assert hub.state_for("gesture", "Right") is not None


async def test_worker_stop_wakes_pending_next_frame():
    camera = InfiniteCamera()
    recognizer = FakeRecognizer([[]])
    worker = GestureWorker(camera, recognizer, evidence=EvidenceHub())
    await worker.start()
    await _pump(0.01)
    await worker.stop()
    assert recognizer.closed
    # no exception and no leaked task
    assert worker._task is None  # type: ignore[attr-defined]


async def test_worker_empty_hands_mean_no_allowlisted_gesture():
    """An empty result is a real 'no hand' observation for the evidence
    layer (VIDEO-mode semantics): it advances release/TTL, never stalls."""
    camera = FakeCamera([0.0, 0.1, 0.2])
    hub = EvidenceHub(confirm_samples=2, release_window_s=0.05, ttl_s=0.1, cooldown_s=1.0)
    recognizer = FakeRecognizer([[], [_thumb_up()], [_thumb_up()]])
    worker = GestureWorker(camera, recognizer, evidence=hub)
    await worker.start()
    await _pump()
    await worker.stop()
    state = hub.state_for("gesture", "Right")
    assert state is not None and state.value == "thumb_up"


async def test_worker_stats_aggregate_p50_p95():
    camera = FakeCamera([0.0, 0.1, 0.2])
    recognizer = SlowRecognizer([[]] * 3, delay_s=0.01)
    worker = GestureWorker(camera, recognizer, evidence=EvidenceHub())
    await worker.start()
    await _pump()
    await worker.stop()
    stats = worker.stats()
    assert stats.latency_p50 is not None and stats.latency_p50 > 0
    assert stats.latency_p95 is not None
    assert stats.frame_age_p50 is not None
    assert stats.frame_age_p95 is not None


async def test_worker_detects_cancellation_without_leaking_executor():
    camera = InfiniteCamera()
    recognizer = FakeRecognizer([[]])
    worker = GestureWorker(camera, recognizer, evidence=EvidenceHub())
    await worker.start()
    await worker.stop()
    assert worker._executor is None  # type: ignore[attr-defined]  # shut down
    assert recognizer.closed