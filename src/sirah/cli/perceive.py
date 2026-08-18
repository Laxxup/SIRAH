"""`sirah-perceive` CLI — diagnostic live perception without moving hardware.

Runs camera -> detector and prints normalized face observations (or "no
face") per frame so an operator can validate camera + YuNet on the target
machine without arming eyes, opening a serial port or actuating servos.

The reusable core is `perceive()`, which satisfies the CameraSource /
FaceDetector contracts and is deterministic-testable with fakes. Exit
codes mirror sirah-runtime: 0 clean, 2 usage error, 1 runtime failure.
A SIGINT/SIGTERM interruption stops the camera cleanly and exits 130.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
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
from sirah.perception.gesture import HandGesture, RawHand


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


@dataclass(frozen=True)
class GesturePreviewObservation:
    """One preview tick with the gesture worker's latest detection snapshot."""

    index: int
    frame_age_s: float | None
    detect_ms: float | None
    target: GazeTarget | None
    states: tuple[StableState, ...]
    events: tuple[str, ...]
    rejected: tuple[RejectedObservation, ...]
    pending: tuple[PendingConfirmation, ...]
    raw_hands: tuple[RawHand, ...]
    hands: tuple[HandGesture, ...]


@dataclass
class GesturePreviewSummary:
    """Face + evidence + gesture diagnostics for one preview run.

    Extends the face-only preview with what MediaPipe saw (raw hands, the
    allowlisted subset) and the worker's own timing so an operator can
    tell exactly why a gesture did or did not become stable state.
    """

    observations: tuple[GesturePreviewObservation, ...]
    faces: int
    all_events: tuple[str, ...]
    rejected_count: int
    detect_ms: tuple[float, ...]
    frame_age_s: tuple[float, ...]
    gesture_inferences: int
    gesture_errors: int
    gesture_latency_ms: tuple[float, ...]
    gesture_frame_age_s: tuple[float, ...]

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

    @property
    def gesture_latency_p50(self) -> float | None:
        return _p50(self.gesture_latency_ms)

    @property
    def gesture_latency_p95(self) -> float | None:
        return _p95(self.gesture_latency_ms)

    @property
    def gesture_frame_age_p50(self) -> float | None:
        return _p50(self.gesture_frame_age_s)

    @property
    def gesture_frame_age_p95(self) -> float | None:
        return _p95(self.gesture_frame_age_s)


async def perceive_gesture_preview(
    camera: CameraSource,
    detector: FaceDetector,
    *,
    gesture_worker,
    viewer=None,
    max_frames: int = 0,
    interval_s: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
    attention: AttentionSelector | None = None,
    evidence: EvidenceHub | None = None,
    camera_stats_provider: Callable[[], object] | None = None,
) -> GesturePreviewSummary:
    """Camera -> YuNet and MediaPipe in parallel, both into one EvidenceHub.

    The face loop and the gesture worker each consume their own broker
    subscription (latest-frame), so neither delays the other. Both feed
    the SAME `EvidenceHub`, which is how a thumb_up becomes stable state
    and an edge event. The gesture worker's latest raw detection is
    snapshotted per tick so the preview can show what MediaPipe saw.

    When `viewer` is provided, each tick also renders a
    `DiagnosticSnapshot` into the viewer; the viewer consumes its own
    broker subscription and never reopens the camera. A user closing the
    viewer window (q/Esc) ends the preview cleanly.
    """
    from sirah.behavior.attention import AttentionManager

    evidence = evidence or EvidenceHub()
    attention = attention or AttentionManager()
    await camera.start()
    await gesture_worker.start()
    if viewer is not None:
        await viewer.start()
    observations: list[GesturePreviewObservation] = []
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
            if viewer is not None and viewer.user_closed:
                break
            now = clock()
            target, detected_faces = _attended(detector, frame, attention, want_faces=viewer is not None)
            snapshot, latency = _evidence_tick(evidence, target, now)
            if target is not None:
                faces += 1
            age = now - frame.captured_at if frame.captured_at is not None else None
            if age is not None:
                frame_ages.append(age)
            detect_ms.append(latency)
            rejected_count += len(snapshot.rejected)
            all_events.extend(snapshot.event_values())
            if viewer is not None:
                viewer.push(_diagnostic_snapshot(frame, now, detected_faces, snapshot, gesture_worker, camera_stats_provider))
            observations.append(
                GesturePreviewObservation(
                    index=frame.index,
                    frame_age_s=age,
                    detect_ms=latency,
                    target=target,
                    states=snapshot.states,
                    events=snapshot.event_values(),
                    rejected=snapshot.rejected,
                    pending=snapshot.pending,
                    raw_hands=gesture_worker.last_raw,
                    hands=gesture_worker.last_hands,
                )
            )
            if max_frames and len(observations) >= max_frames:
                break
            await asyncio.sleep(interval_s)
    finally:
        if viewer is not None:
            await viewer.stop()
        await gesture_worker.stop()
        await camera.stop()
    stats = gesture_worker.stats()
    return GesturePreviewSummary(
        observations=tuple(observations),
        faces=faces,
        all_events=tuple(all_events + list(gesture_worker.emitted_events)),
        rejected_count=rejected_count,
        detect_ms=tuple(detect_ms),
        frame_age_s=tuple(frame_ages),
        gesture_inferences=stats.inferences,
        gesture_errors=stats.errors,
        gesture_latency_ms=stats.latency_ms,
        gesture_frame_age_s=stats.frame_age_s,
    )


async def perceive_preview(
    camera: CameraSource,
    detector: FaceDetector,
    *,
    viewer=None,
    max_frames: int = 0,
    interval_s: float = 0.05,
    clock: Callable[[], float] = time.monotonic,
    attention: AttentionSelector | None = None,
    evidence: EvidenceHub | None = None,
    camera_stats_provider: Callable[[], object] | None = None,
) -> PreviewSummary:
    """Camera → detector → evidence, with full diagnostic reporting.

    The preview routes every detection through the evidence layer
    (`EvidenceHub`) so an operator sees WHY the robot did not react:
    below-confidence rejections, in-progress confirmations, held stable
    states with TTL, and edge events. Requires no GUI; headless text
    output. The camera is always stopped before returning (also on
    cancellation).

    When `viewer` is provided, each tick also renders a
    `DiagnosticSnapshot` into the viewer (faces and face-only evidence;
    no gesture overlays). The viewer consumes its own broker subscription
    and never reopens the camera.
    """
    from sirah.behavior.attention import AttentionManager

    evidence = evidence or EvidenceHub()
    attention = attention or AttentionManager()
    await camera.start()
    if viewer is not None:
        await viewer.start()
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
            if viewer is not None and viewer.user_closed:
                break
            now = clock()
            target, detected_faces = _attended(detector, frame, attention, want_faces=viewer is not None)
            snapshot, latency = _evidence_tick(evidence, target, now)
            if target is not None:
                faces += 1
            age = now - frame.captured_at if frame.captured_at is not None else None
            if age is not None:
                frame_ages.append(age)
            detect_ms.append(latency)
            rejected_count += len(snapshot.rejected)
            all_events.extend(snapshot.event_values())
            if viewer is not None:
                viewer.push(_diagnostic_snapshot(frame, now, detected_faces, snapshot, None, camera_stats_provider))
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
        if viewer is not None:
            await viewer.stop()
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
    detector: FaceDetector,
    frame: Frame,
    attention: AttentionSelector,
    *,
    want_faces: bool = False,
) -> tuple[GazeTarget | None, tuple]:
    """Detector output → attended primary target (attention-aware).

    When `want_faces` is set (graphical viewer active), the detector's
    image-space face boxes are also returned so the viewer can draw real
    bounding boxes and mark the attended target; attention still operates
    on normalized `GazeTarget`s. Returns `(target, faces)` where faces is
    a tuple of `DiagnosticFace` (empty when not requested or unavailable).
    """
    if want_faces:
        boxes = getattr(detector, "detect_boxes", None)
        if callable(boxes):
            from sirah.perception.diagnostic import DiagnosticFace

            payload = frame.payload
            width = height = 1
            if payload is not None and hasattr(payload, "shape") and len(payload.shape) >= 2:
                height, width = payload.shape[:2]
            face_boxes = list(boxes(frame))
            from sirah.perception.yunet import map_face

            targets = [
                map_face(box, width=width, height=height)
                for box in face_boxes
            ]
            attended = attention.observe(targets)
            faces = tuple(
                DiagnosticFace(
                    x=_clamp01(box.x / width) if width else 0.0,
                    y=_clamp01(box.y / height) if height else 0.0,
                    width=_clamp01(box.width / width) if width else 0.0,
                    height=_clamp01(box.height / height) if height else 0.0,
                    confidence=box.confidence,
                    attended=_is_attended_face(attended, target, width, height),
                )
                for box, target in zip(face_boxes, targets)
            )
            return attended, faces
    return _attended_target(detector, frame, attention), ()


def _attended_target(
    detector: FaceDetector, frame: Frame, attention: AttentionSelector
) -> GazeTarget | None:
    if isinstance(detector, MultiFaceDetector):
        return attention.observe(detector.detect_many(frame))
    return detector.detect(frame)


def _clamp01(value: float) -> float:
    """Clamp a normalized coordinate into [0, 1].

    YuNet can report boxes that spill a few pixels past the frame edge;
    the DiagnosticFace contract requires strictly normalized boxes, so the
    snapshot boundary clamps instead of rejecting a real detection.
    """
    return max(0.0, min(1.0, value))


def _is_attended_face(
    attended: GazeTarget | None, target: GazeTarget | None, width: int, height: int
) -> bool:
    """Mark the box whose center maps to the attended target, if any."""
    if attended is None or target is None:
        return False
    return attended.x == target.x and attended.y == target.y


def _diagnostic_snapshot(
    frame: Frame,
    now: float,
    faces: tuple,
    evidence_snapshot: EvidenceSnapshot,
    gesture_worker: object | None,
    camera_stats_provider: Callable[[], object] | None,
):
    """Build the immutable DiagnosticSnapshot for one tick (viewer only)."""
    from sirah.perception.diagnostic import DiagnosticSnapshot

    stats = getattr(gesture_worker, "stats", None)
    worker_stats = stats() if callable(stats) else None
    camera_stats = camera_stats_provider() if camera_stats_provider is not None else None
    return DiagnosticSnapshot(
        frame_index=frame.index,
        created_at=now,
        captured_at=frame.captured_at,
        faces=faces,
        raw_hands=getattr(gesture_worker, "last_raw", ()),
        hands=getattr(gesture_worker, "last_hands", ()),
        states=evidence_snapshot.states,
        events=evidence_snapshot.events,
        rejected=evidence_snapshot.rejected,
        pending=evidence_snapshot.pending,
        camera_fps=_camera_fps(camera_stats),
        camera_captured=_camera_captured(camera_stats),
        gesture_inferences=getattr(worker_stats, "inferences", 0) if worker_stats is not None else 0,
        gesture_errors=getattr(worker_stats, "errors", 0) if worker_stats is not None else 0,
        gesture_latency_ms=getattr(worker_stats, "latency_ms", ()) if worker_stats is not None else (),
        gesture_frame_age_s=getattr(worker_stats, "frame_age_s", ()) if worker_stats is not None else (),
    )


def _camera_fps(stats: object | None) -> float | None:
    fps = getattr(stats, "capture_fps", None)
    return fps if isinstance(fps, float) else None


def _camera_captured(stats: object | None) -> int:
    captured = getattr(stats, "captured", 0)
    return captured if isinstance(captured, int) else 0


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
        "--gesture-model",
        type=Path,
        default=None,
        help="local verified MediaPipe gesture model (gesture_recognizer.task); "
        "enables optional MediaPipe gesture perception alongside YuNet "
        "(requires the 'gesture' extra)",
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
        if args.preview or args.preview_window:
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


async def _gesture_preview_entry(camera: CameraSource, detector: FaceDetector, args: argparse.Namespace) -> int:
    """Diagnostic preview with optional MediaPipe gesture perception.

    The physical camera is owned by a single `FrameBroker`; YuNet and the
    gesture worker each consume their own subscriber (latest-frame), so
    neither delays the other and the camera is opened exactly once. The
    recognizer is built BEFORE the camera is opened: a missing/corrupt
    model or missing 'gesture' extra fails cleanly with a clear message
    and never touches the camera. A MediaPipe failure mid-run is isolated
    in the worker (recorded as gesture errors); YuNet perception and the
    preview continue.
    """
    from sirah.behavior.attention import AttentionManager
    from sirah.perception.evidence import EvidenceHub
    from sirah.perception.fanout import FrameBroker
    from sirah.perception.gesture_worker import GestureWorker
    from sirah.perception.mediapipe_gesture import MediaPipeGestureRecognizer

    recognizer = MediaPipeGestureRecognizer(args.gesture_model)
    hub = EvidenceHub()
    broker = FrameBroker(camera)
    face_camera = broker.subscribe()
    gesture_camera = broker.subscribe()
    worker = GestureWorker(gesture_camera, recognizer, evidence=hub)
    viewer = _make_viewer(broker, args) if args.preview_window else None
    try:
        async with broker:
            summary = await perceive_gesture_preview(
                face_camera,
                detector,
                gesture_worker=worker,
                viewer=viewer,
                max_frames=args.max_frames,
                interval_s=args.interval,
                attention=AttentionManager(),
                evidence=hub,
                camera_stats_provider=lambda: broker.source_stats,
            )
    finally:
        recognizer.close()
    _print_gesture_preview(summary, broker)
    _print_viewer_stats(viewer)
    return 0


def _print_viewer_stats(viewer) -> None:
    if viewer is None:
        return
    stats = viewer.stats
    print(
        f"sirah-perceive: display_fps={_fmt_fps(stats.display_fps)} "
        f"rendered={stats.displayed} render_errors={stats.render_errors} "
        f"out_of_bounds_landmarks={stats.out_of_bounds_landmarks} "
        f"nonfinite_landmarks={stats.nonfinite_landmarks}"
    )


def _fmt_fps(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "n/a"


def _print_gesture_preview(summary: GesturePreviewSummary, broker) -> None:
    for obs in summary.observations:
        print(f"[{obs.index:04d}] age={_fmt_age(obs.frame_age_s)} det={_fmt_ms(obs.detect_ms)}")
        if obs.target is not None:
            print(
                f"    target  x={obs.target.x:+.2f} y={obs.target.y:+.2f} "
                f"conf={obs.target.confidence:.2f}"
            )
        for raw in obs.raw_hands:
            print(
                f"    gesture raw  {raw.handedness.lower()}_hand {raw.category} "
                f"{raw.confidence:.2f}"
            )
        for hand in obs.hands:
            print(
                f"    gesture      {hand.gesture} conf={hand.confidence:.2f} "
                f"({hand.handedness} hand {hand.index})"
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
        if not obs.raw_hands and not obs.states and not obs.events and not obs.rejected and not obs.pending:
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
    print(
        f"sirah-perceive: gesture_inferences={summary.gesture_inferences} "
        f"gesture_errors={summary.gesture_errors} "
        f"latency_p50={_fmt_ms(summary.gesture_latency_p50)} "
        f"latency_p95={_fmt_ms(summary.gesture_latency_p95)} "
        f"frame_age_p50={_fmt_age(summary.gesture_frame_age_p50)} "
        f"frame_age_p95={_fmt_age(summary.gesture_frame_age_p95)}"
    )
    stats = getattr(broker, "source_stats", None)
    if stats is not None:
        print(
            f"sirah-perceive: captured={stats.captured} consumed={stats.consumed} "
            f"dropped={stats.dropped} capture_fps={stats.capture_fps:.1f}"
        )


async def _preview_entry(camera: CameraSource, detector: FaceDetector, args: argparse.Namespace) -> int:
    """Run and print the diagnostic preview (headless, or + graphical)."""
    from sirah.behavior.attention import AttentionManager
    from sirah.perception.evidence import EvidenceHub
    from sirah.perception.fanout import FrameBroker

    if args.preview_window:
        # the viewer needs its own broker subscription; the camera is
        # still owned exactly once, by the broker.
        broker = FrameBroker(camera)
        face_camera = broker.subscribe()
        viewer = _make_viewer(broker, args)
        async with broker:
            summary = await perceive_preview(
                face_camera,
                detector,
                viewer=viewer,
                max_frames=args.max_frames,
                interval_s=args.interval,
                attention=AttentionManager(),
                evidence=EvidenceHub(),
                camera_stats_provider=lambda: broker.source_stats,
            )
        stats_source: object = broker
    else:
        summary = await perceive_preview(
            camera,
            detector,
            max_frames=args.max_frames,
            interval_s=args.interval,
            attention=AttentionManager(),
            evidence=EvidenceHub(),
        )
        stats_source = camera
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
    stats = getattr(stats_source, "source_stats", None) or getattr(stats_source, "stats", None)
    if stats is not None:
        s = stats() if callable(stats) else stats
        print(
            f"sirah-perceive: captured={s.captured} consumed={s.consumed} "
            f"dropped={s.dropped} capture_fps={s.capture_fps:.1f}"
        )
    _print_viewer_stats(viewer if args.preview_window else None)
    return 0


def _make_viewer(broker, args: argparse.Namespace):
    """Build a DiagnosticViewer wired to a fresh broker subscription.

    The viewer consumes the broker's latest frame (it never opens the
    camera) and renders annotated frames to an external ffplay process.
    Building the ffplay backend validates the external executable BEFORE
    the camera is opened, so a missing viewer fails cleanly and never
    touches /dev/videoN. The backend itself is started lazily on the
    first displayed frame.
    """
    from sirah.perception.display import FfplayDisplayBackend
    from sirah.perception.renderer import DiagnosticRenderer
    from sirah.perception.viewer import DiagnosticViewer

    backend = FfplayDisplayBackend()
    renderer = DiagnosticRenderer()
    viewer = DiagnosticViewer(broker.subscribe(), renderer, backend)
    viewer.set_mirror(bool(args.mirror_display))
    return viewer


def _fmt_ttl(expires_at: float | None, observed_at: float) -> str:
    return f"{expires_at - observed_at:.1f}s" if expires_at is not None else "∞"


def _fmt_ms(value: float | None) -> str:
    return f"{value:.1f}ms" if value is not None else "n/a"


if __name__ == "__main__":
    raise SystemExit(main())
