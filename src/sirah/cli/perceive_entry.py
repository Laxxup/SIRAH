"""Live wiring and human-readable output for the perceive CLI entries.

`_preview_entry` and `_gesture_preview_entry` build the real camera,
detector, broker, workers and optional viewer; the `_print_*` helpers
render the summaries for an operator. None of this is exercised by the
deterministic loop tests (those call `perceive_loop` directly).
"""

from __future__ import annotations

import argparse

from sirah.cli.perceive_loop import (
    GesturePreviewSummary,
    perceive_gesture_preview,
    perceive_preview,
)
from sirah.perception.contracts import CameraSource, FaceDetector


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
    person_worker = _make_person_worker(broker, args)
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
                person_worker=person_worker,
            )
    finally:
        recognizer.close()
        if person_worker is not None:
            await person_worker.stop()
    _print_gesture_preview(summary, broker)
    _print_viewer_stats(viewer)
    return 0


def _make_person_worker(broker, args: argparse.Namespace):
    """Build an M6 person detection worker on a fresh broker subscription.

    Returns None when `--person-model` is not set. The MediaPipe person
    detector is built BEFORE the camera is opened: a missing/corrupt model
    or missing mediapipe fails cleanly and never touches the camera. The
    worker consumes its own latest-frame subscription like every other
    consumer; it never opens /dev/videoN.
    """
    if args.person_model is None:
        return None
    from sirah.perception.mediapipe_person import MediaPipePersonDetector
    from sirah.perception.person_worker import PersonDetectionWorker

    detector = MediaPipePersonDetector(args.person_model)
    return PersonDetectionWorker(broker.subscribe(), detector)


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
        for track in obs.person_tracks:
            print(
                f"    person #{track.track_id} {track.lifecycle.value} "
                f"x={track.x:.2f} y={track.y:.2f} w={track.width:.2f} "
                f"h={track.height:.2f} conf={track.confidence:.2f}"
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
        if (
            not obs.person_tracks
            and not obs.raw_hands
            and not obs.states
            and not obs.events
            and not obs.rejected
            and not obs.pending
        ):
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
    if summary.person_inferences or summary.person_latency_ms:
        print(
            f"sirah-perceive: person_inferences={summary.person_inferences} "
            f"person_errors={summary.person_errors} "
            f"latency_p50={_fmt_ms(summary.person_latency_p50)} "
            f"latency_p95={_fmt_ms(summary.person_latency_p95)} "
            f"frame_age_p50={_fmt_age(summary.person_frame_age_p50)} "
            f"frame_age_p95={_fmt_age(summary.person_frame_age_p95)}"
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

    if args.preview_window or args.person_model is not None:
        # the viewer (and the M6 person worker) need their own broker
        # subscriptions; the camera is still owned exactly once, by the
        # broker.
        broker = FrameBroker(camera)
        face_camera = broker.subscribe()
        viewer = _make_viewer(broker, args) if args.preview_window else None
        person_worker = _make_person_worker(broker, args)
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
                person_worker=person_worker,
            )
        if person_worker is not None:
            await person_worker.stop()
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
        for track in obs.person_tracks:
            print(
                f"    person #{track.track_id} {track.lifecycle.value} "
                f"x={track.x:.2f} y={track.y:.2f} w={track.width:.2f} "
                f"h={track.height:.2f} conf={track.confidence:.2f}"
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
        if not obs.person_tracks and not obs.states and not obs.events and not obs.rejected and not obs.pending:
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
    if summary.person_inferences or summary.person_latency_ms:
        print(
            f"sirah-perceive: person_inferences={summary.person_inferences} "
            f"person_errors={summary.person_errors} "
            f"latency_p50={_fmt_ms(summary.person_latency_p50)} "
            f"latency_p95={_fmt_ms(summary.person_latency_p95)} "
            f"frame_age_p50={_fmt_age(summary.person_frame_age_p50)} "
            f"frame_age_p95={_fmt_age(summary.person_frame_age_p95)}"
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