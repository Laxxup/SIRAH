"""M6 person-centric live vision: pure data model and contracts (M6).

SIRAH principle: perception OBSERVES; scene state DESCRIBES. This module is
the person-centric substrate — zero dependencies, deterministic, fully
unit-testable without a camera or model.

Semantics (do not blur these):

- `PersonDetection` is ONE raw detector output: a canonical NON-mirrored
  normalized bbox (x, y, width, height in [0, 1] image units) plus
  confidence and provenance. It is never a human identity.
- `PersonTrack` is a session-local TEMPORAL entity: `track_id` labels a
  bounding-box trajectory in this camera session, NEVER a person. Tracks
  may fragment, switch or reassign after occlusion, crossing or re-entry;
  an id-switch is a tracker reality, not a correctness bug.
- `ObservedScene` is the camera-centric description of "what the camera
  currently observes": OBSERVED NOW / RECENTLY OBSERVED (temporarily_lost)
  / STALE / UNKNOWN. It never invents 3D/world positions, metric distances
  or identity. 2D normalized camera coordinates only.
- TEMPORAL PROVENANCE INVARIANT: every observation carries
  `source_frame_index` (camera sequence), `captured_at` (camera clock) and
  `produced_at` (inference completion). Fusing person/face/hand
  observations from DIFFERENT source frames into one human is forbidden
  without proof of correspondence; `owner = unknown` is a valid result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Protocol, runtime_checkable

from sirah.perception.contracts import Frame


class TrackLifecycle(str, Enum):
    """Session-local track state (never a statement about a human).

    - TENTATIVE: seen too few times to trust as a stable entity;
    - CONFIRMED: currently observed and stable;
    - TEMPORARILY_LOST: last observed recently, then missed by the
      detector — STILL "recently observed at X", never "still at X";
    - EXPIRED: lost longer than the tracker buffer; no longer described.
    """

    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    TEMPORARILY_LOST = "temporarily_lost"
    EXPIRED = "expired"


def _finite_or_raise(name: str, value: float) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


def _normalized_or_raise(name: str, value: float) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be normalized (finite, in [0, 1])")


def box_intersects_frame(x: float, y: float, width: float, height: float) -> bool:
    """True when the box has positive overlap with the normalized frame.

    A person box may legitimately spill a few pixels past the image edge
    (like YuNet face boxes); only boxes FULLY outside the frame are not
    observations at all. Core values are never clamped here — this is
    admission policy, not presentation.
    """
    ix0 = max(x, 0.0)
    iy0 = max(y, 0.0)
    ix1 = min(x + width, 1.0)
    iy1 = min(y + height, 1.0)
    return ix1 > ix0 and iy1 > iy0


@dataclass(frozen=True)
class PersonDetection:
    """One raw person detection (canonical NON-mirrored normalized bbox).

    `source_frame_index` / `captured_at` / `produced_at` are the temporal
    provenance: which camera frame this box came from, when the camera
    captured it, and when inference completed. `detector` names the backend
    so scene consumers can reason about provenance.
    """

    x: float
    y: float
    width: float
    height: float
    confidence: float
    source_frame_index: int
    produced_at: float
    captured_at: float | None = None
    detector: str = "mediapipe_efficientdet_lite0"

    def __post_init__(self) -> None:
        _finite_or_raise("x", self.x)
        _finite_or_raise("y", self.y)
        _finite_or_raise("width", self.width)
        _finite_or_raise("height", self.height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")
        if self.source_frame_index < 0:
            raise ValueError("source_frame_index must not be negative")
        _finite_or_raise("produced_at", self.produced_at)
        if self.captured_at is not None:
            _finite_or_raise("captured_at", self.captured_at)
        if not self.detector:
            raise ValueError("detector must be non-empty")
        if not box_intersects_frame(self.x, self.y, self.width, self.height):
            raise ValueError("detection box must overlap the normalized frame")

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2.0, self.y + self.height / 2.0


@dataclass(frozen=True)
class PersonTrack:
    """A session-local person trajectory at its LATEST known state.

    `velocity` is a normalized-units-per-second estimate (vx, vy) of box
    center motion, or None while there is not enough evidence. A
    TEMPORARILY_LOST track still reports its last observed bbox — that is
    "last seen at X", which the renderer must show distinctly from a
    currently-observed box.
    """

    track_id: int
    lifecycle: TrackLifecycle
    x: float
    y: float
    width: float
    height: float
    confidence: float
    first_seen: float
    last_seen: float
    last_source_frame_index: int
    detector: str = "mediapipe_efficientdet_lite0"
    velocity: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.track_id < 0:
            raise ValueError("track_id must not be negative")
        _finite_or_raise("x", self.x)
        _finite_or_raise("y", self.y)
        _finite_or_raise("width", self.width)
        _finite_or_raise("height", self.height)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")
        _finite_or_raise("first_seen", self.first_seen)
        _finite_or_raise("last_seen", self.last_seen)
        if self.first_seen > self.last_seen:
            raise ValueError("first_seen must not be after last_seen")
        if self.last_source_frame_index < 0:
            raise ValueError("last_source_frame_index must not be negative")
        if not self.detector:
            raise ValueError("detector must be non-empty")
        if self.velocity is not None:
            vx, vy = self.velocity
            _finite_or_raise("velocity.vx", vx)
            _finite_or_raise("velocity.vy", vy)

    @property
    def observed_now(self) -> bool:
        """True only when the track is currently observed, not just known."""
        return self.lifecycle in (TrackLifecycle.TENTATIVE, TrackLifecycle.CONFIRMED)


@dataclass(frozen=True)
class ObservedScene:
    """Camera-centric description of the people this camera observes.

    `tracks` are ordered for deterministic rendering (active confirmed,
    then tentative, then temporarily_lost, each by ascending track_id).
    `observed_at` is the monotonic time the scene was assembled;
    `source_frame_index` is the camera frame the tracks derive from. A
    consumer MUST NOT present tracks whose `source_frame_index` is newer
    than the frame it is describing.
    """

    tracks: tuple[PersonTrack, ...]
    observed_at: float
    source_frame_index: int
    camera_fps: float | None = None

    def __post_init__(self) -> None:
        _finite_or_raise("observed_at", self.observed_at)
        if self.source_frame_index < 0:
            raise ValueError("source_frame_index must not be negative")
        if self.camera_fps is not None and (
            self.camera_fps < 0 or not isfinite(self.camera_fps)
        ):
            raise ValueError("camera_fps must be finite and non-negative")

    @property
    def active(self) -> tuple[PersonTrack, ...]:
        """Tracks currently observed now (tentative + confirmed)."""
        return tuple(track for track in self.tracks if track.observed_now)

    @property
    def person_count(self) -> int:
        """People the camera CURRENTLY observes (never lost tracks)."""
        return len(self.active)

    @property
    def person_present(self) -> bool:
        return self.person_count > 0

    @property
    def temporarily_lost(self) -> tuple[PersonTrack, ...]:
        return tuple(
            track
            for track in self.tracks
            if track.lifecycle is TrackLifecycle.TEMPORARILY_LOST
        )


@runtime_checkable
class PersonDetector(Protocol):
    """Frame -> zero or more canonical person detections.

    Detectors OBSERVE; they never own the camera, never decide behavior and
    never assign identity. Implementations return detections from a single
    frame (provenance attached). A blank frame yields an empty tuple.
    """

    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]: ...


@runtime_checkable
class PersonTracker(Protocol):
    """Temporal association: per-frame detections -> session-local tracks.

    The tracker is called once per processed frame with that frame's
    detections and its source frame index; it is never fed fused data from
    multiple frames. `now` is the monotonic assembly time for freshness.
    """

    def update(
        self,
        detections: tuple[PersonDetection, ...] | list[PersonDetection],
        *,
        source_frame_index: int,
        now: float,
    ) -> tuple[PersonTrack, ...]: ...