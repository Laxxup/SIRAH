"""Frame → diagnostic snapshot transforms for the perceive CLI previews.

The graphical (`--preview-window`) and gesture preview loops call these
helpers to turn one detector tick into the attended target, the image-space
face boxes and the `DiagnosticSnapshot` fed to the viewer. Pure
transformations over the perception contracts: no camera, model or hardware
access.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sirah.behavior.contracts import AttentionSelector
from sirah.perception.contracts import (
    FaceDetector,
    Frame,
    GazeTarget,
    MultiFaceDetector,
)
from sirah.perception.evidence import EvidenceHub, EvidenceSnapshot


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
    person_worker: object | None = None,
):
    """Build the immutable DiagnosticSnapshot for one tick (viewer only)."""
    from sirah.perception.diagnostic import DiagnosticSnapshot

    stats = getattr(gesture_worker, "stats", None)
    worker_stats = stats() if callable(stats) else None
    person_stats = getattr(person_worker, "stats", None)
    p_stats = person_stats() if callable(person_stats) else None
    camera_stats = camera_stats_provider() if camera_stats_provider is not None else None
    return DiagnosticSnapshot(
        frame_index=frame.index,
        created_at=now,
        captured_at=frame.captured_at,
        faces=faces,
        raw_hands=getattr(gesture_worker, "last_raw", ()),
        hands=getattr(gesture_worker, "last_hands", ()),
        person_tracks=_person_tracks(person_worker, frame.index),
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
        person_inferences=getattr(p_stats, "inferences", 0) if p_stats is not None else 0,
        person_errors=getattr(p_stats, "errors", 0) if p_stats is not None else 0,
        person_latency_ms=getattr(p_stats, "latency_ms", ()) if p_stats is not None else (),
        person_frame_age_s=getattr(p_stats, "frame_age_s", ()) if p_stats is not None else (),
    )


def _person_tracks(person_worker: object | None, frame_index: int) -> tuple:
    """Person tracks for a displayed frame, temporally aligned.

    The worker's scene is only used when its `source_frame_index` is not
    newer than the frame being described — a detection from a future frame
    is never painted onto an older frame (temporal provenance invariant).
    """
    if person_worker is None:
        return ()
    scene_for = getattr(person_worker, "scene_for", None)
    if not callable(scene_for):
        return ()
    scene = scene_for(frame_index)
    return getattr(scene, "tracks", ())


def _camera_fps(stats: object | None) -> float | None:
    fps = getattr(stats, "capture_fps", None)
    return fps if isinstance(fps, float) else None


def _camera_captured(stats: object | None) -> int:
    captured = getattr(stats, "captured", 0)
    return captured if isinstance(captured, int) else 0


def _evidence_tick(
    evidence: EvidenceHub, target: GazeTarget | None, now: float
) -> tuple[EvidenceSnapshot, float]:
    """Feed the attended face into evidence; measure detector latency."""
    from sirah.perception.vision_context import face_observation

    started = time.monotonic()
    snapshot = evidence.observe([face_observation(target, now=now)], now=now)
    latency_ms = (time.monotonic() - started) * 1000.0
    return snapshot, latency_ms