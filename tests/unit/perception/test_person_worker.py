"""PersonDetectionWorker tests (M6): off-loop detection+tracking, broker
integration, latest-frame semantics, temporal alignment, isolation and
clean shutdown — over fakes, no mediapipe, no hardware."""

from __future__ import annotations

import asyncio
import time

from sirah.perception.contracts import Frame
from sirah.perception.fanout import FrameBroker
from sirah.perception.person import PersonDetection
from sirah.perception.person_tracker import GreedyIoUTracker
from sirah.perception.person_worker import PersonDetectionWorker


class FakePersonDetector:
    def __init__(self, per_frame: list[list[PersonDetection]]) -> None:
        self._per_frame = list(per_frame)
        self.closed = False
        self.calls = 0

    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]:
        detections = self._per_frame[min(self.calls, len(self._per_frame) - 1)]
        self.calls += 1
        return tuple(detections)

    def close(self) -> None:
        self.closed = True


class SlowPersonDetector(FakePersonDetector):
    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]:
        time.sleep(0.02)
        return super().detect_persons(frame)


class ThrowingPersonDetector(FakePersonDetector):
    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]:
        raise RuntimeError("person model crashed")


class FakeCamera:
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
    def __init__(self) -> None:
        super().__init__([])
        self._frames = [0.0]

    async def next_frame(self) -> Frame | None:
        await asyncio.sleep(0)
        frame = Frame(index=self._index, payload=None, captured_at=float(self._index))
        self._index += 1
        return frame


def _det(x: float, fidx: int, t: float, conf: float = 0.9) -> PersonDetection:
    return PersonDetection(
        x=x, y=0.2, width=0.3, height=0.6, confidence=conf,
        source_frame_index=fidx, produced_at=t,
    )


async def _pump(seconds: float = 0.05) -> None:
    await asyncio.sleep(seconds)


async def test_worker_produces_scene_and_temporal_alignment():
    camera = FakeCamera([0.0, 0.1, 0.2])
    detector = FakePersonDetector([[_det(0.2, 0, 0.0)], [_det(0.2, 1, 0.1)], [_det(0.2, 2, 0.2)]])
    worker = PersonDetectionWorker(camera, detector, tracker=GreedyIoUTracker())
    await worker.start()
    await _pump()
    await worker.stop()

    scene = worker.last_scene
    assert scene is not None
    assert scene.source_frame_index == 2
    assert scene.person_count == 1
    # scene_for never hands out a NEWER scene for an older frame
    assert worker.scene_for(0) is None  # scene (source 2) is newer than frame 0
    assert worker.scene_for(1) is None  # scene (source 2) is newer than frame 1
    assert worker.scene_for(2) is scene
    assert worker.scene_for(3) is scene  # older scene on a newer frame is fine
    assert detector.closed
    assert camera.stops == 0


async def test_worker_isolates_detector_failure():
    camera = FakeCamera([0.0, 0.1, 0.2])
    detector = ThrowingPersonDetector([])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump()
    await worker.stop()
    assert worker.stats().errors == 3
    assert worker.stats().inferences == 0
    assert worker.last_scene is None
    # an exception must not leak into the caller / YuNet pipeline


async def test_worker_keeps_last_scene_on_late_failure():
    """A mid-run failure keeps the last VALID scene (never a fabricated one)."""
    camera = FakeCamera([0.0, 0.1, 0.2, 0.3])

    class LaterThrower(FakePersonDetector):
        def detect_persons(self, frame: Frame):
            if self.calls >= 2:
                raise RuntimeError("crash")
            return super().detect_persons(frame)

    detector = LaterThrower([[_det(0.2, 0, 0.0)], [_det(0.2, 1, 0.1)], [], []])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump()
    await worker.stop()
    assert worker.stats().errors >= 2
    assert worker.last_scene is not None
    assert worker.last_scene.source_frame_index == 1


async def test_worker_skips_intermediate_frames_for_slow_detector():
    camera = InfiniteCamera()
    detector = SlowPersonDetector([[_det(0.2, 0, 0.0)], [_det(0.7, 0, 0.0)]])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump(0.2)
    await worker.stop()
    # while inference was busy the broker advanced: far fewer frames processed
    assert detector.calls < 20
    scene = worker.last_scene
    assert scene is not None and scene.source_frame_index > 0


async def test_worker_fills_latency_and_frame_age():
    camera = FakeCamera([10.0, 10.1, 10.2])
    detector = FakePersonDetector([[], [], []])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump()
    await worker.stop()
    stats = worker.stats()
    assert stats.latency_ms
    assert stats.frame_age_s
    assert all(age >= 0 for age in stats.frame_age_s)


async def test_worker_async_context_manager_closes():
    camera = FakeCamera([0.0, 0.1])
    detector = FakePersonDetector([[], []])
    worker = PersonDetectionWorker(camera, detector)
    async with worker:
        await _pump()
    assert detector.closed


async def test_worker_integration_with_frame_broker():
    source = FakeCamera([float(i) for i in range(20)])
    broker = FrameBroker(source)
    face_camera = broker.subscribe()
    person_camera = broker.subscribe()
    detector = FakePersonDetector([[_det(0.2, 0, 0.0)]])
    worker = PersonDetectionWorker(person_camera, detector)

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
    assert detector.calls >= 2
    assert worker.last_scene is not None


async def test_worker_stop_wakes_pending_next_frame():
    camera = InfiniteCamera()
    detector = FakePersonDetector([[]])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump(0.01)
    await worker.stop()
    assert detector.closed
    assert worker._task is None  # type: ignore[attr-defined]


async def test_worker_detects_cancellation_without_leaking_executor():
    camera = InfiniteCamera()
    detector = FakePersonDetector([[]])
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await worker.stop()
    assert worker._executor is None  # type: ignore[attr-defined]
    assert detector.closed


async def test_worker_stats_aggregate_p50_p95():
    camera = FakeCamera([0.0, 0.1, 0.2])
    detector = SlowPersonDetector([[]] * 3)
    worker = PersonDetectionWorker(camera, detector)
    await worker.start()
    await _pump()
    await worker.stop()
    stats = worker.stats()
    assert stats.latency_p50 is not None and stats.latency_p50 > 0
    assert stats.latency_p95 is not None
    assert stats.frame_age_p50 is not None
    assert stats.frame_age_p95 is not None