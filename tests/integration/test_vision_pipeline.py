"""M8.1: the vision pipeline serves the full vertical slice over fakes.

Camera -> YuNet-style face -> optional gesture/person workers -> shared
EvidenceHub -> PerceptionFacts -> WorldState -> VisionContext. Everything
runs on fakes: no OpenCV, models or hardware. These tests exercise the
real broker/worker wiring, so they live in integration.
"""

from __future__ import annotations

import asyncio
import time

from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.gesture import GestureDetection, HandGesture
from sirah.perception.person import PersonDetection
from sirah.perception.vision_pipeline import VisionPipeline


class PacedCamera:
    def __init__(self, count: int, interval_s: float = 0.02) -> None:
        self._count = count
        self._interval = interval_s
        self._index = 0
        self.stopped = False

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        if self._index >= self._count:
            return None
        if self._interval:
            await asyncio.sleep(self._interval)
        frame = Frame(
            index=self._index, payload=None, captured_at=float(self._index)
        )
        self._index += 1
        return frame

    async def stop(self) -> None:
        self.stopped = True


class FakeFaceDetector:
    def detect_many(self, frame: Frame) -> list[GazeTarget]:
        return [GazeTarget(0.2, -0.3, 0.9)]


class FakePersonDetector:
    def __init__(self) -> None:
        self.closed = False

    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]:
        return (
            PersonDetection(
                0.3,
                0.2,
                0.4,
                0.6,
                0.95,
                frame.index,
                produced_at=float(frame.index),
                captured_at=frame.captured_at,
            ),
        )

    def close(self) -> None:
        self.closed = True


class FakeGestureRecognizer:
    def __init__(self) -> None:
        self.closed = False

    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        return GestureDetection(
            hands=(HandGesture("thumb_up", 0.9, "Right", 0),),
            raw=(),
            timestamp_ms=frame.index,
        )

    def close(self) -> None:
        self.closed = True


async def _wait_for(
    pipeline: VisionPipeline, predicate, timeout_s: float = 3.0
) -> str | None:
    deadline = time.monotonic() + timeout_s
    text: str | None = None
    while time.monotonic() < deadline:
        text = pipeline.vision_context()
        if predicate(text):
            return text
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out; last context: {text!r}")


async def test_pipeline_serves_person_face_gesture_and_worldstate():
    camera = PacedCamera(count=40, interval_s=0.02)
    pipeline = VisionPipeline(
        camera=camera,
        face_detector=FakeFaceDetector(),
        gesture_recognizer=FakeGestureRecognizer(),
        person_detector=FakePersonDetector(),
    )

    def ready(text: str | None) -> bool:
        return bool(
            text
            and "Persona" in text
            and "Un rostro está visible." in text
            and "Gesto: thumb_up." in text
        )

    async with pipeline:
        text = await _wait_for(pipeline, ready)

    assert "Persona visible: #0." in text
    assert "Un rostro está visible." in text
    assert "Gesto: thumb_up." in text
    assert pipeline.errors == 0
    assert not pipeline.degraded
    world = pipeline.world_state
    assert world is not None
    assert world.face_present
    assert world.perception is not None
    assert camera.stopped


async def test_pipeline_without_person_detector_reports_face_only():
    camera = PacedCamera(count=10, interval_s=0.02)
    pipeline = VisionPipeline(camera=camera, face_detector=FakeFaceDetector())

    async with pipeline:
        text = await _wait_for(
            pipeline, lambda t: t is not None and "Un rostro está visible." in t
        )

    assert "Personas visibles" not in text
    assert "Un rostro está visible." in text
    assert pipeline.errors == 0


async def test_pipeline_stop_is_idempotent_and_closes_adapters():
    person = FakePersonDetector()
    gesture = FakeGestureRecognizer()
    camera = PacedCamera(count=5, interval_s=0.02)
    pipeline = VisionPipeline(
        camera=camera,
        face_detector=FakeFaceDetector(),
        gesture_recognizer=gesture,
        person_detector=person,
    )

    async with pipeline:
        pass
    await pipeline.stop()  # second stop must be harmless

    assert camera.stopped
    assert person.closed
    assert gesture.closed
