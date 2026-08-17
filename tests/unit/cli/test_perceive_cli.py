"""sirah-perceive tests: the reusable perceive() core over fakes is
deterministic and needs no OpenCV, model, camera or hardware."""

from __future__ import annotations

import pytest

from sirah.cli.perceive import build_parser, perceive
from sirah.perception.contracts import Frame, GazeTarget


class FakeCamera:
    def __init__(self, frames: list[object]) -> None:
        self._frames = iter(frames)
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def next_frame(self) -> Frame | None:
        try:
            payload = next(self._frames)
        except StopIteration:
            return None
        return Frame(index=payload[0], payload=None, captured_at=payload[1])

    async def stop(self) -> None:
        self.stopped = True


class FakeDetector:
    def __init__(self, targets: dict[int, GazeTarget | None]) -> None:
        self._targets = targets

    def detect(self, frame: Frame) -> GazeTarget | None:
        return self._targets.get(frame.index)


async def test_perceive_reports_faces_and_absence():
    camera = FakeCamera([(0, 100.0), (1, 100.2), (2, 100.4), (3, 100.6)])
    detector = FakeDetector(
        {
            0: GazeTarget(0.5, -0.5, 0.9),
            2: GazeTarget(-0.2, 0.1, 0.7),
        }
    )
    summary = await perceive(camera, detector, max_frames=4, clock=lambda: 100.6)
    assert summary.frames == 4
    assert summary.faces == 2
    assert camera.started and camera.stopped
    assert summary.observations[0].target == GazeTarget(0.5, -0.5, 0.9)
    assert summary.observations[0].frame_age_s == pytest.approx(0.6)
    assert summary.observations[1].target is None


async def test_perceive_stops_on_source_exhaustion():
    camera = FakeCamera([(0, 100.0), (1, 100.1)])
    detector = FakeDetector({0: GazeTarget(0.0, 0.0)})
    summary = await perceive(camera, detector, max_frames=0)
    assert summary.frames == 2
    assert camera.stopped


async def test_perceive_stops_after_max_frames():
    camera = FakeCamera([(0, 1.0), (1, 2.0), (2, 3.0), (3, 4.0)])
    detector = FakeDetector({})
    summary = await perceive(camera, detector, max_frames=2, interval_s=0.0)
    assert summary.frames == 2
    assert camera.stopped


async def test_perceive_stops_camera_on_detector_failure():
    camera = FakeCamera([(0, 1.0), (1, 2.0)])

    class ExplodingDetector:
        def detect(self, frame: Frame) -> GazeTarget | None:
            raise RuntimeError("detector crashed")

    try:
        await perceive(camera, ExplodingDetector(), max_frames=0)
    except RuntimeError:
        pass
    assert camera.stopped  # teardown still ran


def test_parser_requires_exactly_one_source_and_model():
    parser = build_parser()
    args = parser.parse_args(
        ["--camera-device", "/dev/video0", "--yunet-model", "yunet.onnx", "--max-frames", "10"]
    )
    assert args.camera_device == "/dev/video0"
    assert args.yunet_model == "yunet.onnx"
    assert args.max_frames == 10