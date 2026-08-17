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
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sirah.behavior.contracts import AttentionSelector
from sirah.perception.contracts import (
    CameraSource,
    FaceDetector,
    Frame,
    GazeTarget,
    MultiFaceDetector,
)
from sirah.perception.evidence import (
    EvidenceHub,
    EvidenceSnapshot,
    PendingConfirmation,
    RawObservation,
    RejectedObservation,
    StableState,
)


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


@dataclass(frozen=True)
class PreviewObservation:
    """One preview tick: raw/stable/rejected/pending for a single frame."""

    index: int
    frame_age_s: float | None
    detect_ms: float | None
    target: GazeTarget | None
    states: tuple[StableState, ...]
    events: tuple[str, ...]
    rejected: tuple[RejectedObservation, ...]
    pending: tuple[PendingConfirmation, ...]


@dataclass
class PreviewSummary:
    """Diagnostic view answering 'why did SIRAH not react?'."""

    observations: tuple[PreviewObservation, ...]
    faces: int
    all_events: tuple[str, ...]
    rejected_count: int
    detect_ms: tuple[float, ...]
    frame_age_s: tuple[float, ...]

    @property
    def frames(self) -> int:
        return len(self.observations)

    @property
    def detect_p50(self) -> float | None:
        return _p50(self.detect_ms)

    @property
    def detect_p95(self) -> float | None:
        return _p95(self.detect_ms)

    @property
    def frame_age_p50(self) -> float | None:
        return _p50(self.frame_age_s)

    @property
    def frame_age_p95(self) -> float | None:
        return _p95(self.frame_age_s)


def _p50(values: tuple[float, ...]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _p95(values: tuple[float, ...]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return round(ordered[index], 3)


async def perceive_preview(
    camera: CameraSource,
    detector: FaceDetector,
    *,
    max_frames: int = 0,
    interval_s: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
    attention: AttentionSelector | None = None,
    evidence: EvidenceHub | None = None,
) -> PreviewSummary:
    """Camera → detector → evidence, with full diagnostic reporting.

    The preview routes every detection through the evidence layer
    (`EvidenceHub`) so an operator sees WHY the robot did not react:
    below-confidence rejections, in-progress confirmations, held stable
    states with TTL, and edge events. Requires no GUI; headless text
    output. The camera is always stopped before returning (also on
    cancellation).
    """
    from sirah.behavior.attention import AttentionManager

    evidence = evidence or EvidenceHub()
    attention = attention or AttentionManager()
    await camera.start()
    observations: list[PreviewObservation] = []
    faces = 0
    all_events: list[str] = []
    rejected_count = 0
    detect_ms: list[float] = []
    frame_ages: list[float] = []
    try:
        while True:
            frame = await camera.next_frame()
            if frame is None:
                break
            now = clock()
            target = _attended(detector, frame, attention)
            snapshot, latency = _evidence_tick(evidence, target, now)
            if target is not None:
                faces += 1
            age = now - frame.captured_at if frame.captured_at is not None else None
            if age is not None:
                frame_ages.append(age)
            detect_ms.append(latency)
            rejected_count += len(snapshot.rejected)
            all_events.extend(snapshot.event_values())
            observations.append(
                PreviewObservation(
                    index=frame.index,
                    frame_age_s=age,
                    detect_ms=latency,
                    target=target,
                    states=snapshot.states,
                    events=snapshot.event_values(),
                    rejected=snapshot.rejected,
                    pending=snapshot.pending,
                )
            )
            if max_frames and len(observations) >= max_frames:
                break
            await asyncio.sleep(interval_s)
    finally:
        await camera.stop()
    return PreviewSummary(
        observations=tuple(observations),
        faces=faces,
        all_events=tuple(all_events),
        rejected_count=rejected_count,
        detect_ms=tuple(detect_ms),
        frame_age_s=tuple(frame_ages),
    )


def _attended(
    detector: FaceDetector, frame: Frame, attention: AttentionSelector
) -> GazeTarget | None:
    """Detector output → attended primary target (attention-aware)."""
    if isinstance(detector, MultiFaceDetector):
        return attention.observe(detector.detect_many(frame))
    return detector.detect(frame)


def _evidence_tick(
    evidence: EvidenceHub, target: GazeTarget | None, now: float
) -> tuple[EvidenceSnapshot, float]:
    """Feed the attended person into evidence; measure detector latency."""
    started = time.monotonic()
    if target is not None:
        raws = [
            RawObservation(
                "yunet",
                "person",
                "present",
                target.confidence,
                now,
                "primary",
            )
        ]
    else:
        # confidence 0.0 surfaces as a below-confidence rejection diagnostic
        raws = [
            RawObservation("yunet", "person", "present", 0.0, now, "primary")
        ]
    snapshot = evidence.observe(raws, now=now)
    latency_ms = (time.monotonic() - started) * 1000.0
    return snapshot, latency_ms


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
    parser.add_argument(
        "--preview",
        action="store_true",
        help="diagnostic mode: route through the evidence layer and report "
        "raw/stable/rejected observations, events, TTL and detector latency "
        "(answers 'why did SIRAH not react?'; headless, no GUI)",
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
        if args.preview:
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


def _fmt_age(age: float | None) -> str:
    return f"{age:.2f}s" if age is not None else "n/a"


async def _preview_entry(camera: CameraSource, detector: FaceDetector, args: argparse.Namespace) -> int:
    """Run and print the diagnostic preview (headless)."""
    from sirah.behavior.attention import AttentionManager
    from sirah.perception.evidence import EvidenceHub

    summary = await perceive_preview(
        camera,
        detector,
        max_frames=args.max_frames,
        interval_s=args.interval,
        attention=AttentionManager(),
        evidence=EvidenceHub(),
    )
    for obs in summary.observations:
        print(f"[{obs.index:04d}] age={_fmt_age(obs.frame_age_s)} det={_fmt_ms(obs.detect_ms)}")
        if obs.target is not None:
            print(
                f"    target  x={obs.target.x:+.2f} y={obs.target.y:+.2f} "
                f"conf={obs.target.confidence:.2f}"
            )
        for state in obs.states:
            age = obs.frame_age_s if obs.frame_age_s is not None else 0.0
            print(
                f"    stable  {state.kind}={state.value} conf={state.confidence:.2f} "
                f"age={age:.2f}s ttl={_fmt_ttl(state.expires_at, state.observed_at)}"
            )
        for event in obs.events:
            print(f"    EVENT   {event}")
        for rejected in obs.rejected:
            print(
                f"    REJECT  {rejected.raw.kind}={rejected.raw.value} "
                f"conf={rejected.raw.confidence:.2f} reason={rejected.reason.value}"
            )
        for pending in obs.pending:
            print(
                f"    confirm {pending.kind}={pending.value} "
                f"{pending.confirm_count}/{pending.confirm_samples}"
            )
        if not obs.states and not obs.events and not obs.rejected and not obs.pending:
            print("    (nothing stable yet)")
    print(
        f"sirah-perceive: frames={summary.frames} faces={summary.faces} "
        f"events={summary.all_events or '—'} rejected={summary.rejected_count}"
    )
    print(
        f"sirah-perceive: detect_p50={_fmt_ms(summary.detect_p50)} "
        f"detect_p95={_fmt_ms(summary.detect_p95)} "
        f"frame_age_p50={_fmt_age(summary.frame_age_p50)} "
        f"frame_age_p95={_fmt_age(summary.frame_age_p95)}"
    )
    stats = getattr(camera, "stats", None)
    if stats is not None:
        s = stats()
        print(
            f"sirah-perceive: captured={s.captured} consumed={s.consumed} "
            f"dropped={s.dropped} capture_fps={s.capture_fps:.1f}"
        )
    return 0


def _fmt_ms(value: float | None) -> str:
    return f"{value:.1f}ms" if value is not None else "n/a"


def _fmt_ttl(expires_at: float | None, observed_at: float) -> str:
    return f"{expires_at - observed_at:.1f}s" if expires_at is not None else "∞"


if __name__ == "__main__":
    raise SystemExit(main())
