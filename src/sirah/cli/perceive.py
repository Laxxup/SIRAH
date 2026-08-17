"""`sirah-perceive` CLI — diagnostic live perception without moving hardware.

Runs camera -> detector and prints normalized face observations (or "no
face") per frame so an operator can validate camera + YuNet on the target
machine without arming eyes, opening a serial port or actuating servos.

The reusable core is `perceive()`, which satisfies the CameraSource /
FaceDetector contracts and is deterministic-testable with fakes. Exit
codes mirror sirah-runtime: 0 clean, 2 usage error, 1 runtime failure.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sirah.perception.contracts import CameraSource, FaceDetector, GazeTarget


@dataclass(frozen=True)
class PerceptionObservation:
    """One diagnostic cycle: the frame index, its detected target (or None)."""

    index: int
    target: GazeTarget | None
    frame_age_s: float | None


@dataclass
class PerceptionSummary:
    observations: tuple[PerceptionObservation, ...]
    faces: int

    @property
    def frames(self) -> int:
        return len(self.observations)


async def perceive(
    camera: CameraSource,
    detector: FaceDetector,
    *,
    max_frames: int = 0,
    interval_s: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
) -> PerceptionSummary:
    """Camera → detector for `max_frames` (0 = until the source ends).

    `next_frame` blocks asynchronously until a frame is available, so an
    active camera with a slow first frame is awaited, not mistaken for
    end-of-stream (None now means EOF only). Never touches behavior,
    transport or hardware beyond the camera. The camera is always stopped
    before returning (also on cancellation).
    """
    await camera.start()
    observations: list[PerceptionObservation] = []
    faces = 0
    try:
        while True:
            frame = await camera.next_frame()
            if frame is None:
                break
            target = detector.detect(frame)
            if target is not None:
                faces += 1
            age = clock() - frame.captured_at if frame.captured_at is not None else None
            observations.append(PerceptionObservation(frame.index, target, age))
            if max_frames and len(observations) >= max_frames:
                break
            await asyncio.sleep(interval_s)
    finally:
        await camera.stop()
    return PerceptionSummary(tuple(observations), faces)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sirah-perceive",
        description="Diagnostic live perception: camera → face detector, "
        "printing normalized observations without moving hardware.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--camera-device",
        default=None,
        help="USB camera device (e.g. /dev/video0); requires --yunet-model",
    )
    source.add_argument(
        "--replay-jsonl",
        type=Path,
        default=None,
        help="JSONL image replay manifest; requires --yunet-model",
    )
    source.add_argument(
        "--replay-video",
        type=Path,
        default=None,
        help="video replay file; requires --yunet-model",
    )
    parser.add_argument("--yunet-model", required=True, help="local verified YuNet ONNX model")
    parser.add_argument(
        "--max-frames", type=int, default=0, help="stop after N frames (0 = until the source ends)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.05, help="seconds between frame reads (default 0.05)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_frames < 0:
        build_parser().error("--max-frames must not be negative")
    return asyncio.run(_entry(args))


async def _entry(args: argparse.Namespace) -> int:
    from sirah.perception.opencv_camera import OpenCVCameraSource
    from sirah.perception.replay import (
        OpenCVJsonlReplayCameraSource,
        VideoReplayCameraSource,
    )
    from sirah.perception.yunet import YuNetFaceDetector

    if args.camera_device:
        camera: CameraSource = OpenCVCameraSource(args.camera_device)
    elif args.replay_jsonl:
        camera = OpenCVJsonlReplayCameraSource(args.replay_jsonl)
    else:
        camera = VideoReplayCameraSource(args.replay_video)
    detector: FaceDetector = YuNetFaceDetector(Path(args.yunet_model))

    try:
        summary = await perceive(
            camera, detector, max_frames=args.max_frames, interval_s=args.interval
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic tool reports and exits
        print(f"sirah-perceive: {exc}", file=sys.stderr)
        return 1

    for obs in summary.observations:
        if obs.target is not None:
            print(
                f"[{obs.index:04d}] face x={obs.target.x:+.2f} y={obs.target.y:+.2f} "
                f"conf={obs.target.confidence:.2f} age={_fmt_age(obs.frame_age_s)}"
            )
        else:
            print(f"[{obs.index:04d}] no face age={_fmt_age(obs.frame_age_s)}")
    print(f"sirah-perceive: frames={summary.frames} faces={summary.faces}")
    stats = getattr(camera, "stats", None)
    if stats is not None:
        s = stats()
        print(
            f"sirah-perceive: captured={s.captured} consumed={s.consumed} "
            f"dropped={s.dropped} capture_fps={s.capture_fps:.1f}"
        )
    return 0


def _fmt_age(age: float | None) -> str:
    return f"{age:.2f}s" if age is not None else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
