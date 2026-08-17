"""sirah-perceive tests: the reusable perceive() core over fakes is
deterministic and needs no OpenCV, model, camera or hardware."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import sirah.cli.perceive as perceive_cli
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


def test_parser_gesture_model_is_optional():
    parser = build_parser()
    without = parser.parse_args(["--camera-device", "/dev/video0", "--yunet-model", "yunet.onnx"])
    assert without.gesture_model is None
    with_gesture = parser.parse_args(
        [
            "--camera-device",
            "/dev/video0",
            "--yunet-model",
            "yunet.onnx",
            "--gesture-model",
            "gesture.task",
        ]
    )
    assert with_gesture.gesture_model == Path("gesture.task")


def test_parser_preview_window_and_mirror_flags():
    parser = build_parser()
    args = parser.parse_args(
        ["--camera-device", "/dev/video0", "--yunet-model", "yunet.onnx", "--preview-window"]
    )
    assert args.preview_window is True
    assert args.mirror_display is False
    mirrored = parser.parse_args(
        [
            "--camera-device",
            "/dev/video0",
            "--yunet-model",
            "yunet.onnx",
            "--preview-window",
            "--mirror-display",
        ]
    )
    assert mirrored.mirror_display is True


def test_make_viewer_raises_actionable_error_when_ffplay_missing(monkeypatch, tmp_path):
    import sirah.cli.perceive as perceive_cli
    import sirah.perception.display as display_mod

    def missing(_executable: str) -> str | None:
        return None

    monkeypatch.setattr(display_mod, "_which_ffplay", missing)
    from sirah.perception.fanout import FrameBroker

    broker = FrameBroker(FakeCamera([]))
    parser = build_parser()
    args = parser.parse_args(
        ["--camera-device", "/dev/video0", "--yunet-model", str(tmp_path / "yunet.onnx")]
    )
    with pytest.raises(RuntimeError, match="ffplay"):
        perceive_cli._make_viewer(broker, args)


def test_preview_window_routes_to_preview_entry(monkeypatch, tmp_path):
    """--preview-window alone (no gesture model) must go to the preview path,
    not the headless perceive() path."""
    import sirah.cli.perceive as perceive_cli
    import sirah.perception.opencv_camera as opencv_camera_mod
    import sirah.perception.yunet as yunet_mod

    model = tmp_path / "yunet.onnx"
    model.touch()

    class FakeOpenCVSource:
        def __init__(self, *args, **kwargs):
            pass

    class FakeYuNet:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(opencv_camera_mod, "OpenCVCameraSource", FakeOpenCVSource)
    monkeypatch.setattr(yunet_mod, "YuNetFaceDetector", FakeYuNet)

    calls: list[str] = []

    async def fake_preview_entry(camera, detector, args):
        calls.append("preview_entry")
        return 0

    async def fake_perceive(camera, detector, **kwargs):
        calls.append("perceive")

    monkeypatch.setattr(perceive_cli, "_preview_entry", fake_preview_entry)
    monkeypatch.setattr(perceive_cli, "perceive", fake_perceive)

    asyncio.run(
        perceive_cli._entry(
            build_parser().parse_args(
                ["--camera-device", "/dev/video0", "--yunet-model", str(model), "--preview-window"]
            )
        )
    )
    assert calls == ["preview_entry"]


def test_main_handles_ctrl_c_without_a_traceback(monkeypatch, capsys):
    """A SIGINT cancellation must exit cleanly, not leak a traceback."""

    def interrupt(_coroutine):
        _coroutine.close()
        raise asyncio.CancelledError

    monkeypatch.setattr(perceive_cli.asyncio, "run", interrupt)
    assert (
        perceive_cli.main(["--camera-device", "/dev/video0", "--yunet-model", "yunet.onnx"])
        == 130
    )


def test_main_handles_keyboard_interrupt_without_a_traceback(monkeypatch, capsys):
    def interrupt(_coroutine):
        _coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(perceive_cli.asyncio, "run", interrupt)
    assert (
        perceive_cli.main(["--camera-device", "/dev/video0", "--yunet-model", "yunet.onnx"])
        == 130
    )


async def test_perceive_stops_camera_on_cancellation():
    """CANCELLATION: an interrupted perceive still stops the camera."""
    camera = FakeCamera([(0, 1.0), (1, 2.0)])
    task = asyncio.create_task(
        perceive(camera, FakeDetector({}), max_frames=0, interval_s=5.0)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert camera.stopped  # teardown still ran during cancellation