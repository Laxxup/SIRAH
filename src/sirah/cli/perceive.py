"""`sirah-perceive` CLI — diagnostic live perception without moving hardware.

Runs camera -> detector and prints normalized face observations (or "no
face") per frame so an operator can validate camera + YuNet on the target
machine without arming eyes, opening a serial port or actuating servos.

This module is the CLI boundary: argument parsing, `main`, signal handling
and mode routing (`_entry`). The deterministic loops live in
`perceive_loop`, the frame→snapshot transforms in `perceive_snapshot`, and
the live wiring plus output in `perceive_entry`. The names below are
re-exported from those modules so `sirah-perceive` and existing tests keep
working unchanged.

Exit codes mirror sirah-runtime: 0 clean, 2 usage error, 1 runtime failure.
A SIGINT/SIGTERM interruption stops the camera cleanly and exits 130.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from sirah.cli.perceive_entry import (
    _fmt_age,
    _fmt_fps,
    _fmt_ms,
    _fmt_ttl,
    _gesture_preview_entry,
    _make_person_worker,
    _make_viewer,
    _preview_entry,
    _print_gesture_preview,
    _print_viewer_stats,
)
from sirah.cli.perceive_loop import (
    GesturePreviewObservation,
    GesturePreviewSummary,
    PerceptionObservation,
    PerceptionSummary,
    PreviewObservation,
    PreviewSummary,
    perceive,
    perceive_gesture_preview,
    perceive_preview,
)
from sirah.perception.contracts import CameraSource, FaceDetector

__all__ = [
    "GesturePreviewObservation",
    "GesturePreviewSummary",
    "PerceptionObservation",
    "PerceptionSummary",
    "PreviewObservation",
    "PreviewSummary",
    "_entry",
    "_entry_with_signal_stop",
    "_fmt_age",
    "_fmt_fps",
    "_fmt_ms",
    "_fmt_ttl",
    "_gesture_preview_entry",
    "_make_person_worker",
    "_make_viewer",
    "_preview_entry",
    "_print_gesture_preview",
    "_print_viewer_stats",
    "build_parser",
    "main",
    "perceive",
    "perceive_gesture_preview",
    "perceive_preview",
]


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
        "--gesture-model",
        type=Path,
        default=None,
        help="local verified MediaPipe gesture model (gesture_recognizer.task); "
        "enables optional MediaPipe gesture perception alongside YuNet "
        "(requires the 'gesture' extra)",
    )
    parser.add_argument(
        "--person-model",
        type=Path,
        default=None,
        help="local verified MediaPipe person model (efficientdet_lite0.tflite, "
        "see 'sirah-models person'); enables M6 person-centric live tracking "
        "alongside YuNet (requires the 'gesture' extra; implies preview)",
    )
    parser.add_argument(
        "--max-frames", type=int, default=0, help="stop after N frames (0 = until the source ends)"
    )
    parser.add_argument(
        "--interval", type=float, default=0.05, help="seconds between frame reads (default 0.05)"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="diagnostic mode: route through the evidence layer and report "
        "raw/stable/rejected observations, events, TTL and detector latency "
        "(answers 'why did SIRAH not react?'; headless, no GUI)",
    )
    parser.add_argument(
        "--preview-window",
        action="store_true",
        help="graphical diagnostic mode: open a live annotated camera view "
        "(faces, attended target, hand landmarks, raw vs stable gestures, "
        "events and freshness/performance HUD) via an external ffplay "
        "window. The camera is still owned once by the frame broker. "
        "Requires the external 'ffplay' executable (part of FFmpeg). "
        "May be combined with --preview for text + window.",
    )
    parser.add_argument(
        "--mirror-display",
        action="store_true",
        help="presentation-only horizontal mirror for --preview-window "
        "(rendering transform x' = width-1-x; never alters stored "
        "coordinates or perception data)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_frames < 0:
        build_parser().error("--max-frames must not be negative")
    try:
        return asyncio.run(_entry_with_signal_stop(args))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nsirah-perceive: stopping...", file=sys.stderr)
        return 130


async def _entry_with_signal_stop(args: argparse.Namespace) -> int:
    """Run the entry point, converting SIGINT/SIGTERM into a clean cancellation.

    A Ctrl-C cancels the running perception task so the camera is still
    stopped cleanly in `_entry`'s teardown (no `ioctl(VIDIOC_QBUF)`
    warning, no traceback). The signal handler is idempotent, so a
    repeated signal just re-requests the same cancellation; `main` maps
    the resulting `CancelledError` (or any `KeyboardInterrupt`) to exit
    code 130.
    """
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None

    def _request_stop(*_args: object) -> None:
        if not task.done():
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:  # Windows fallback
            signal.signal(sig, lambda *_args: _request_stop())
    return await _entry(args)


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
        if args.gesture_model is not None:
            return await _gesture_preview_entry(camera, detector, args)
        if args.preview or args.preview_window or args.person_model is not None:
            return await _preview_entry(camera, detector, args)
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


if __name__ == "__main__":
    raise SystemExit(main())