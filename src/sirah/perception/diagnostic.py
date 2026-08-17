"""Diagnostic snapshot for the graphical perception viewer (M5.2B).

The viewer must never open the camera: it consumes a `FrameBroker`
subscription like every other consumer. To draw what perception actually
saw, the perceive loop emits one immutable `DiagnosticSnapshot` per
processed frame — the smallest bundle of raw + stable + performance data
needed to explain "what did SIRAH see, and how fresh is it?".

Temporal correspondence is explicit: the snapshot records the source
`frame_index`/`captured_at` and the monotonic `created_at` of the
snapshot itself, so the renderer can decide whether overlays are fresh,
stale (dim + STALE tag) or too old to draw at all — it never silently
paints stale landmarks onto a newer frame. All face boxes are stored
normalized (0..1) so the renderer projects them onto whatever frame size
it is handed; mirroring stays a pure presentation transform.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from sirah.perception.evidence import (
    PendingConfirmation,
    RejectedObservation,
    StableEvent,
    StableState,
)
from sirah.perception.gesture import HandGesture, RawHand


def _normalized(value: float) -> bool:
    return 0.0 <= value <= 1.0


def _finite_or_raise(name: str, value: float | None) -> None:
    if value is not None and not isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class DiagnosticFace:
    """One detected face in normalized image coordinates (0..1).

    `attended` marks the primary target chosen by the attention layer for
    the frame this snapshot describes, so the renderer can draw it
    distinctly from faces that were merely detected.
    """

    x: float
    y: float
    width: float
    height: float
    confidence: float
    attended: bool = False

    def __post_init__(self) -> None:
        if not all(_normalized(v) for v in (self.x, self.y, self.width, self.height)):
            raise ValueError("face box must be normalized")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")


@dataclass(frozen=True)
class DiagnosticSnapshot:
    """One immutable view of perception for one source frame.

    `created_at` is a monotonic clock reading captured when the snapshot
    was built, so `now - created_at` is the overlay's presentation age.
    `frame_index`/`captured_at` identify the source frame the detection
    data belongs to; the renderer uses them to bound how old an overlay
    may be before it is marked stale or dropped.
    """

    frame_index: int
    created_at: float
    captured_at: float | None
    faces: tuple[DiagnosticFace, ...] = ()
    raw_hands: tuple[RawHand, ...] = ()
    hands: tuple[HandGesture, ...] = ()
    states: tuple[StableState, ...] = ()
    events: tuple[StableEvent, ...] = ()
    rejected: tuple[RejectedObservation, ...] = ()
    pending: tuple[PendingConfirmation, ...] = ()
    camera_fps: float | None = None
    camera_captured: int = 0
    gesture_inferences: int = 0
    gesture_errors: int = 0
    gesture_latency_ms: tuple[float, ...] = ()
    gesture_frame_age_s: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must not be negative")
        if not isfinite(self.created_at):
            raise ValueError("created_at must be finite")
        _finite_or_raise("captured_at", self.captured_at)
        for value in self.gesture_latency_ms:
            if value < 0 or not isfinite(value):
                raise ValueError("gesture latency values must be finite and non-negative")
        for value in self.gesture_frame_age_s:
            if value < 0 or not isfinite(value):
                raise ValueError("gesture frame ages must be finite and non-negative")
        if self.camera_fps is not None and (self.camera_fps < 0 or not isfinite(self.camera_fps)):
            raise ValueError("camera_fps must be finite and non-negative")

    def event_ttl_elapsed(self, now: float, ttl_s: float) -> tuple[StableEvent, ...]:
        """Edge events still within a presentation-only TTL at `now`.

        This is display-only accounting; the evidence layer's own
        semantics are never changed by it.
        """
        return tuple(event for event in self.events if now - event.observed_at <= ttl_s)
