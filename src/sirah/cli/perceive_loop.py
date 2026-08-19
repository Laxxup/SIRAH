"""Deterministic perception loops for the `sirah-perceive` CLI.

`perceive()`, `perceive_preview()` and `perceive_gesture_preview()` drive
camera → detector → evidence over the provided contracts and collect a
deterministic summary. They never open hardware: tests exercise them with
fakes. The frame→snapshot transforms they call live in `perceive_snapshot`.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

from sirah.behavior.contracts import AttentionSelector
from sirah.cli.perceive_snapshot import (
    _attended,
    _diagnostic_snapshot,
    _evidence_tick,
    _person_tracks,
)
from sirah.perception.contracts import CameraSource, FaceDetector, GazeTarget
from sirah.perception.evidence import (
    EvidenceHub,
    PendingConfirmation,
    RejectedObservation,
    StableState,
)
from sirah.perception.gesture import HandGesture, RawHand
from sirah.perception.person import PersonTrack


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
    person_tracks: tuple[PersonTrack, ...] = ()


@dataclass
class PreviewSummary:
    """Diagnostic view answering 'why did SIRAH not react?'."""

    observations: tuple[PreviewObservation, ...]
    faces: int
    all_events: tuple[str, ...]
    rejected_count: int
    detect_ms: tuple[float, ...]
    frame_age_s: tuple[float, ...]
    person_inferences: int = 0
    person_errors: int = 0
    person_latency_ms: tuple[float, ...] = ()
    person_frame_age_s: tuple[float, ...] = ()

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
    def person_latency_p50(self) -> float | None:
        return _p50(self.person_latency_ms)

    @property
    def person_latency_p95(self) -> float | None:
        return _p95(self.person_latency_ms)

    @property
    def person_frame_age_p50(self) -> float | None:
        return _p50(self.person_frame_age_s)

    @property
    def person_frame_age_p95(self) -> float | None:
        return _p95(self.person_frame_age_s)


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
    person_tracks: tuple[PersonTrack, ...] = ()


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
    person_inferences: int = 0
    person_errors: int = 0
    person_latency_ms: tuple[float, ...] = ()
    person_frame_age_s: tuple[float, ...] = ()

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

    @property
    def person_latency_p50(self) -> float | None:
        return _p50(self.person_latency_ms)

    @property
    def person_latency_p95(self) -> float | None:
        return _p95(self.person_latency_ms)

    @property
    def person_frame_age_p50(self) -> float | None:
        return _p50(self.person_frame_age_s)

    @property
    def person_frame_age_p95(self) -> float | None:
        return _p95(self.person_frame_age_s)


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
    person_worker=None,
) -> GesturePreviewSummary:
    """Camera -> YuNet, MediaPipe gestures and (optionally) person tracking,
    in parallel, each on its own broker subscription.

    The face loop, the gesture worker and the person worker each consume
    their own broker subscription (latest-frame), so none delays the
    others. The gesture worker's latest raw detection and the person
    worker's latest scene are snapshotted per tick; person tracks are only
    attached when their source frame is not newer than the tick's frame
    (temporal provenance). When `viewer` is provided, each tick renders a
    `DiagnosticSnapshot` into the viewer; the viewer consumes its own
    broker subscription and never reopens the camera. A user closing the
    viewer window (q/Esc) ends the preview cleanly.
    """
    from sirah.behavior.attention import AttentionManager

    evidence = evidence or EvidenceHub()
    attention = attention or AttentionManager()
    await camera.start()
    await gesture_worker.start()
    if person_worker is not None:
        await person_worker.start()
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
            person_tracks = _person_tracks(person_worker, frame.index)
            if viewer is not None:
                viewer.push(_diagnostic_snapshot(frame, now, detected_faces, snapshot, gesture_worker, camera_stats_provider, person_worker))
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
                    person_tracks=person_tracks,
                )
            )
            if max_frames and len(observations) >= max_frames:
                break
            await asyncio.sleep(interval_s)
    finally:
        if viewer is not None:
            await viewer.stop()
        await gesture_worker.stop()
        if person_worker is not None:
            await person_worker.stop()
        await camera.stop()
    stats = gesture_worker.stats()
    person_stats = person_worker.stats() if person_worker is not None else None
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
        person_inferences=person_stats.inferences if person_stats else 0,
        person_errors=person_stats.errors if person_stats else 0,
        person_latency_ms=person_stats.latency_ms if person_stats else (),
        person_frame_age_s=person_stats.frame_age_s if person_stats else (),
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
    person_worker=None,
) -> PreviewSummary:
    """Camera → detector → evidence, with full diagnostic reporting.

    The preview routes every detection through the evidence layer
    (`EvidenceHub`) so an operator sees WHY the robot did not react:
    below-confidence rejections, in-progress confirmations, held stable
    states with TTL, and edge events. Requires no GUI; headless text
    output. The camera is always stopped before returning (also on
    cancellation).

    When `person_worker` is provided, person tracking runs in parallel on
    its own broker subscription and its scene is snapshotted per tick
    (only when its source frame is not newer than the tick's frame). When
    `viewer` is provided, each tick also renders a `DiagnosticSnapshot`
    into the viewer (faces and face-only evidence; no gesture overlays).
    The viewer consumes its own broker subscription and never reopens the
    camera.
    """
    from sirah.behavior.attention import AttentionManager

    evidence = evidence or EvidenceHub()
    attention = attention or AttentionManager()
    await camera.start()
    if person_worker is not None:
        await person_worker.start()
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
            person_tracks = _person_tracks(person_worker, frame.index)
            if viewer is not None:
                viewer.push(_diagnostic_snapshot(frame, now, detected_faces, snapshot, None, camera_stats_provider, person_worker))
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
                    person_tracks=person_tracks,
                )
            )
            if max_frames and len(observations) >= max_frames:
                break
            await asyncio.sleep(interval_s)
    finally:
        if viewer is not None:
            await viewer.stop()
        if person_worker is not None:
            await person_worker.stop()
        await camera.stop()
    person_stats = person_worker.stats() if person_worker is not None else None
    return PreviewSummary(
        observations=tuple(observations),
        faces=faces,
        all_events=tuple(all_events),
        rejected_count=rejected_count,
        detect_ms=tuple(detect_ms),
        frame_age_s=tuple(frame_ages),
        person_inferences=person_stats.inferences if person_stats else 0,
        person_errors=person_stats.errors if person_stats else 0,
        person_latency_ms=person_stats.latency_ms if person_stats else (),
        person_frame_age_s=person_stats.frame_age_s if person_stats else (),
    )