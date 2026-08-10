"""`sirah-runtime` CLI — launch the stable runtime (Stage 7).

Single-authority rule (ADR-0002/0009): the runtime app OWNS the serial
port; this CLI only builds components and delegates. It never opens the
port itself. Exit codes: 0 clean stop, 2 usage error, 1 runtime error.
`--fake` selects the FakeESP32 twin for no-hardware runs (ADR-0010).
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from sirah.config.loader import DEFAULT_SERIAL_DEVICE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sirah-runtime",
        description="SIRAH v0.3.0 stable eye runtime (Milestone 1; "
        "subsistema de ojos de SIRAH — Sistema Inteligente Robótico de "
        "Asistencia Humana).",
    )
    parser.add_argument(
        "--eyes",
        action="store_true",
        help="arm the eyes subsystem (default: disarmed, SIRAH_EYES=0; "
        "overrides SIRAH_EYES if both present — env wins on explicit value)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help=f"serial device (default: {DEFAULT_SERIAL_DEVICE}; "
        "allowlist /dev/ttyUSB* or /dev/sirah-eyes, ADR-0002)",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="use the in-memory FakeESP32 twin (no hardware, ADR-0010)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="runtime TOML path (default: config/runtime.toml, A9)",
    )
    parser.add_argument(
        "--actuators",
        default=None,
        help="actuator mirror YAML path (default: config/actuators.yaml, A9)",
    )
    parser.add_argument(
        "--lab",
        action="store_true",
        help="enable the laboratory proposal source (ADR-0007, default off)",
    )
    parser.add_argument(
        "--camera-device",
        default=None,
        help="USB camera device; requires --yunet-model",
    )
    parser.add_argument(
        "--yunet-model",
        default=None,
        help="local verified YuNet ONNX model; requires --camera-device",
    )
    parser.add_argument(
        "--replay-jsonl",
        default=None,
        help="JSONL image replay; requires --yunet-model",
    )
    parser.add_argument(
        "--replay-video",
        default=None,
        help="video replay; requires --yunet-model",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log component statuses"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sources = [args.camera_device, args.replay_jsonl, args.replay_video]
    if sum(source is not None for source in sources) > 1:
        parser.error("choose only one of --camera-device, --replay-jsonl, or --replay-video")
    if bool(any(sources)) != bool(args.yunet_model):
        parser.error("a camera or replay source and --yunet-model must be supplied together")
    return asyncio.run(_entry(args))


async def _entry(args: argparse.Namespace) -> int:
    from sirah.behavior.gaze_behavior import GazeBehavior
    from sirah.config.loader import load_runtime_config
    from sirah.hardware.fake_esp32 import FakeESP32
    from sirah.hardware.serial_adapter import SerialTransport
    from sirah.hardware.transport import EyeTransport
    from sirah.perception.contracts import CameraSource
    from sirah.perception.opencv_camera import OpenCVCameraSource
    from sirah.perception.replay import (
        OpenCVJsonlReplayCameraSource,
        VideoReplayCameraSource,
    )
    from sirah.perception.yunet import YuNetFaceDetector
    from sirah.runtime.app import RuntimeApp
    from sirah.runtime.registry import ComponentStatus

    env = dict(__import__("os").environ)
    if args.eyes:
        env["SIRAH_EYES"] = "1"
    if args.lab:
        env["SIRAH_LAB"] = "1"
    if args.device:
        env["SIRAH_SERIAL_DEVICE"] = args.device

    settings, actuators = load_runtime_config(args.config, args.actuators, env)

    if not settings.serial_device_is_allowlisted:
        print(
            f"sirah-runtime: device '{settings.serial_device}' not allowlisted "
            "(ADR-0002: /dev/ttyUSB* or /dev/sirah-eyes)",
            file=sys.stderr,
        )
        return 2

    if args.fake:
        transport: EyeTransport = FakeESP32.from_actuators_yaml(args.actuators)
    else:
        transport = SerialTransport(
            device=settings.serial_device,
            baudrate=settings.baudrate,
        )
    camera: CameraSource | None = None
    detector = behavior = None
    if args.camera_device:
        camera = OpenCVCameraSource(args.camera_device)
    elif args.replay_jsonl:
        camera = OpenCVJsonlReplayCameraSource(Path(args.replay_jsonl))
    elif args.replay_video:
        camera = VideoReplayCameraSource(Path(args.replay_video))
    if camera is not None:
        detector = YuNetFaceDetector(Path(args.yunet_model))
        behavior = GazeBehavior()
    app = RuntimeApp(
        settings, actuators, transport, camera=camera, face_detector=detector, behavior=behavior
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows fallback
            signal.signal(sig, lambda *_: stop.set())

    if args.verbose:
        print(f"sirah-runtime: boot {settings.serial_device} "
              f"eyes={settings.eyes_armed} lab={settings.lab_enabled}")

    result = await app.run(stop)
    states = result.registry.snapshot()
    if args.verbose:
        for name, state in states.items():
            print(f"  [{state.status}] {name}: {state.detail}")

    degraded = [
        name for name, s in states.items()
        if s.status == ComponentStatus.DEGRADED
    ]
    if degraded:
        print(
            "sirah-runtime: degraded components: " + ", ".join(sorted(degraded)),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
