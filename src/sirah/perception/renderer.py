"""Deterministic diagnostic renderer (M5.2B/5.2C).

Turns a camera frame + `DiagnosticSnapshot` into an annotated BGR image.
The renderer is pure and display-independent:

- it consumes only SIRAH-normalized data (normalized face boxes, SIRAH's
  normalized 21-point hand landmarks) — never MediaPipe internals;
- it uses only `cv2` imgproc primitives that exist in
  `opencv-python-headless`, so the graphical preview never forces a GUI
  OpenCV build onto the production dependency tree;
- it never mutates the shared broker frame: it draws on a private copy;
- all geometry is projected through pure helpers, so mirroring (`x' =
  width-1-x`) is a presentation-only transform applied to every overlay
  without touching the underlying stored coordinates;
- it is fully testable without a display server, windowing system or
  ffplay.

Overlay semantics are explicit:

- RAW perception (detected faces, MediaPipe-reported raw hand categories
  and landmarks) is drawn differently from STABLE evidence (the
  allowlisted gesture that reached the evidence layer);
- events are edge events shown only within a presentation-only TTL;
- overlays whose source frame is too old are dimmed and tagged STALE,
  and beyond the hard drop age they are not drawn at all — stale
  detections are never silently painted onto a newer frame.

Off-frame robustness (M5.2C): a hand landmark that MediaPipe reports
just outside the image (a hand entering/leaving the frame) is NOT a
pipeline failure. This renderer follows MediaPipe's own drawing parity:
a finite landmark with no drawable pixel is skipped, and a connection is
drawn only when both endpoints are drawable. Non-finite landmarks are
skipped and counted. Core landmark values are never mutated or clamped;
only their *projection* is presentation policy. The face path keeps the
strict normalized-invariant projection because face boxes are guaranteed
normalized at the snapshot boundary.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.gesture import HandGesture, Landmark, RawHand
from sirah.perception.person import PersonTrack, TrackLifecycle

_LOGGER = logging.getLogger(__name__)

# Rate limit for repeating anomaly warnings: bounded, not every frame.
_ANOMALY_LOG_INTERVAL_S = 5.0

# SIRAH consumes MediaPipe's normalized 21-point hand topology; the
# renderer only needs that topology as plain indices, never the vendor
# types.
HAND_EDGES: Final[tuple[tuple[int, int], ...]] = (
    (0, 1), (1, 2), (2, 3), (3, 4),  # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),  # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),  # ring
    (0, 17), (17, 18), (18, 19), (19, 20),  # pinky
)

# BGR colors
_COLOR_FACE = (0, 200, 0)
_COLOR_ATTENDED = (0, 160, 255)
_COLOR_HAND = (255, 180, 0)
_COLOR_HAND_ATTENDED = (255, 0, 255)
_COLOR_RAW = (0, 220, 255)
_COLOR_STABLE = (80, 255, 80)
_COLOR_EVENT = (255, 255, 0)
_COLOR_PERF = (220, 220, 220)
_COLOR_STALE = (120, 120, 120)
_COLOR_PERSON = (0, 180, 255)  # confirmed person (BGR orange)
_COLOR_PERSON_TENTATIVE = (0, 120, 200)  # too few hits yet
_COLOR_PERSON_LOST = (130, 130, 130)  # recently observed, not current

FONT = None  # resolved lazily to avoid importing cv2 at module import time


@dataclass(frozen=True)
class RenderContext:
    """Presentation parameters for one render call.

    `now` is a monotonic clock used to bound overlay age. `mirror` is a
    rendering-only horizontal flip applied to every overlay. `display_fps`
    is fed back into the HUD so the operator can see how the viewer is
    keeping up with the camera.
    """

    now: float
    mirror: bool = False
    display_fps: float | None = None


def project_x(x: float, width: int, *, mirror: bool = False) -> int:
    """Map a normalized x coordinate to a pixel column.

    When `mirror` is set the transform `x' = width - 1 - x` is applied to
    every normalized x before projecting, which is the canonical
    presentation-only mirror for a rendered image.
    """
    if not 0.0 <= x <= 1.0:
        raise ValueError("normalized x must be in [0, 1]")
    if width <= 0:
        raise ValueError("width must be positive")
    projected = x * (width - 1)
    if mirror:
        projected = (width - 1) - projected
    return round(projected)


def project_y(y: float, height: int) -> int:
    """Map a normalized y coordinate to a pixel row."""
    if not 0.0 <= y <= 1.0:
        raise ValueError("normalized y must be in [0, 1]")
    if height <= 0:
        raise ValueError("height must be positive")
    return round(y * (height - 1))


def hand_pixel(
    x: float,
    y: float,
    width: int,
    height: int,
    *,
    mirror: bool = False,
) -> tuple[int, int] | None:
    """Tolerant projection for diagnostic hand landmarks.

    Returns pixel coordinates only when the point is drawable: both
    normalized coordinates must be finite AND within [0, 1]. A finite
    point just outside the image (MediaPipe reports these while a hand
    enters/leaves the frame) and any non-finite value return `None` —
    MediaPipe parity: an undrawable landmark has no pixel coordinate and
    is skipped by the caller, never converted to an integer pixel.

    Core landmark values are never modified or clamped here; this is
    purely a presentation transform. `width`/`height` must be positive.
    """
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
        return None
    px = round(x * (width - 1))
    py = round(y * (height - 1))
    if mirror:
        px = (width - 1) - px
    return px, py


def raw_hand_label(raw: RawHand) -> str:
    """Presentation label for raw perception: MediaPipe-reported data."""
    return f"{raw.handedness.lower()} hand {raw.category} {raw.confidence:.2f}"


def stable_hand_label(hand: HandGesture) -> str:
    """Presentation label for an allowlisted gesture observation."""
    return f"{hand.gesture} {hand.confidence:.2f} ({hand.handedness} hand)"


class DiagnosticRenderer:
    """Pure renderer: (Frame, DiagnosticSnapshot | None) -> annotated BGR copy.

    Aggregate anomaly counters (`out_of_bounds_landmarks`,
    `nonfinite_landmarks`, `render_errors`) make the diagnostic viewer
    observable without logging every occurrence: the first occurrence of
    each class is logged with full detail, later ones are rate-limited.
    """

    def __init__(
        self,
        *,
        event_ttl_s: float = 2.0,
        stale_after_s: float = 0.25,
        drop_after_s: float = 1.0,
    ) -> None:
        if event_ttl_s < 0:
            raise ValueError("event_ttl_s must not be negative")
        if not 0.0 < stale_after_s < drop_after_s:
            raise ValueError("require 0 < stale_after_s < drop_after_s")
        self.event_ttl_s = event_ttl_s
        self.stale_after_s = stale_after_s
        self.drop_after_s = drop_after_s
        self.out_of_bounds_landmarks = 0
        self.nonfinite_landmarks = 0
        self.render_errors = 0
        self._oob_first_logged = False
        self._nonfinite_first_logged = False
        self._last_oob_log: float | None = None
        self._last_nonfinite_log: float | None = None

    def render(
        self,
        frame: Frame,
        snapshot: DiagnosticSnapshot | None,
        context: RenderContext,
    ) -> object:
        """Annotated copy of `frame.payload` (BGR numpy array), unmutated input.

        Returns a numpy BGR image; the shared broker frame is never
        modified. When the payload is missing a plain black canvas of a
        reasonable default size is returned so the viewer keeps rendering.
        """
        import cv2

        payload = frame.payload
        if payload is None:
            canvas = _black_canvas()
            _draw_hud(cv2, canvas, snapshot, context, display_fps=context.display_fps)
            return canvas
        import numpy as np

        out = np.array(payload, copy=True)  # never mutate the shared frame
        height, width = out.shape[:2]
        _draw_hud(cv2, out, snapshot, context, display_fps=context.display_fps)
        if snapshot is None:
            return out
        age = context.now - snapshot.created_at
        if age >= self.drop_after_s:
            return out  # overlays too old to draw at all
        stale = age >= self.stale_after_s
        _draw_overlays(
            cv2,
            out,
            snapshot,
            width,
            height,
            mirror=context.mirror,
            stale=stale,
            now=context.now,
            event_ttl_s=self.event_ttl_s,
            renderer=self,
        )
        return out


def _black_canvas():
    import numpy as np

    return np.zeros((480, 640, 3), dtype=np.uint8)


def _draw_hud(cv2, canvas, snapshot: DiagnosticSnapshot | None, context: RenderContext, *, display_fps: float | None) -> None:
    lines: list[str] = []
    if snapshot is None:
        lines.append("awaiting first detection...")
    else:
        lines.append(f"cam {_fmt_fps(snapshot.camera_fps)}  frame #{snapshot.frame_index}")
        lat = snapshot.gesture_latency_ms
        if lat:
            p50, p95 = _percentiles(lat)
            lines.append(f"gesture p50 {p50:.1f}ms p95 {p95:.1f}ms")
        age = snapshot.gesture_frame_age_s
        if age:
            p50a, p95a = _percentiles(age)
            lines.append(f"gesture frame age p50 {p50a:.3f}s p95 {p95a:.3f}s")
        if snapshot.gesture_errors:
            lines.append(f"gesture errors {snapshot.gesture_errors}")
        if snapshot.person_tracks:
            active = [t for t in snapshot.person_tracks if t.observed_now]
            lost = [t for t in snapshot.person_tracks if not t.observed_now]
            lines.append(f"person {len(active)}" + (f" ({len(lost)} lost)" if lost else ""))
        person_lat = snapshot.person_latency_ms
        if person_lat:
            p50, p95 = _percentiles(person_lat)
            lines.append(f"person p50 {p50:.1f}ms p95 {p95:.1f}ms")
        person_age = snapshot.person_frame_age_s
        if person_age:
            p50a, p95a = _percentiles(person_age)
            lines.append(f"person frame age p50 {p50a:.3f}s p95 {p95a:.3f}s")
        if snapshot.person_errors:
            lines.append(f"person errors {snapshot.person_errors}")
    if display_fps is not None:
        lines.append(f"display {display_fps:.1f} fps")
    _draw_text_block(cv2, canvas, lines, x=6, y=14, size=0.5, color=_COLOR_PERF)


def _draw_overlays(
    cv2,
    out,
    snapshot: DiagnosticSnapshot,
    width: int,
    height: int,
    *,
    mirror: bool,
    stale: bool,
    now: float,
    event_ttl_s: float,
    renderer: DiagnosticRenderer,
) -> None:
    for face in snapshot.faces:
        _draw_face(cv2, out, face, width, height, mirror=mirror, stale=stale)
    for track in snapshot.person_tracks:
        _draw_person(cv2, out, track, width, height, mirror=mirror, stale=stale)
    for index, raw in enumerate(snapshot.raw_hands):
        stable = _matching_hand(snapshot.hands, index, raw.index)
        _draw_hand(
            cv2,
            out,
            raw,
            stable,
            width,
            height,
            mirror=mirror,
            stale=stale,
            now=now,
            frame_index=snapshot.frame_index,
            renderer=renderer,
        )
    _draw_evidence(cv2, out, snapshot, width, stale=stale)
    _draw_events(cv2, out, snapshot, now, event_ttl_s, width, stale=stale)
    if stale:
        _draw_text_block(cv2, out, ["STALE"], x=6, y=height - 6, size=0.6, color=_COLOR_STALE)


def _draw_face(cv2, out, face, width: int, height: int, *, mirror: bool, stale: bool) -> None:
    x0 = project_x(face.x, width, mirror=mirror)
    y0 = project_y(face.y, height)
    x1 = project_x(min(1.0, face.x + face.width), width, mirror=mirror)
    y1 = project_y(min(1.0, face.y + face.height), height)
    color = _COLOR_ATTENDED if face.attended else _COLOR_FACE
    if stale:
        color = _COLOR_STALE
    thickness = 2 if face.attended else 1
    cv2.rectangle(out, (x0, y0), (x1, y1), color, thickness)
    label = f"{face.confidence:.2f}" + (" T" if face.attended else "")
    _draw_text(cv2, out, label, x0, max(0, y0 - 5), size=0.4, color=color)
    if face.attended:
        cx = project_x(face.x + face.width / 2, width, mirror=mirror)
        cy = project_y(face.y + face.height / 2, height)
        _draw_crosshair(cv2, out, cx, cy, color)


def _draw_crosshair(cv2, out, cx: int, cy: int, color) -> None:
    cv2.line(out, (cx - 8, cy), (cx + 8, cy), color, 1)
    cv2.line(out, (cx, cy - 8), (cx, cy + 8), color, 1)


def _project_person_box(
    track: PersonTrack, width: int, height: int, *, mirror: bool
) -> tuple[int, int, int, int]:
    """Presentation-only projection of a person box.

    A person box may legitimately spill a few pixels past the frame edge
    (the observation stays canonical and truthful); projection clips to
    the image because pixels outside it are not drawable. This is the same
    tolerant-clip policy the hand path uses for entering/leaving landmarks
    — an undrawable part is skipped, never a pipeline failure.
    """
    x0 = project_x(max(0.0, min(1.0, track.x)), width, mirror=mirror)
    y0 = project_y(max(0.0, min(1.0, track.y)), height)
    x1 = project_x(max(0.0, min(1.0, track.x + track.width)), width, mirror=mirror)
    y1 = project_y(max(0.0, min(1.0, track.y + track.height)), height)
    return x0, y0, x1, y1


def _draw_person(
    cv2,
    out,
    track: PersonTrack,
    width: int,
    height: int,
    *,
    mirror: bool,
    stale: bool,
) -> None:
    x0, y0, x1, y1 = _project_person_box(track, width, height, mirror=mirror)
    if track.lifecycle is TrackLifecycle.CONFIRMED:
        color, thickness = _COLOR_PERSON, 2
    elif track.lifecycle is TrackLifecycle.TENTATIVE:
        color, thickness = _COLOR_PERSON_TENTATIVE, 1
    else:  # TEMPORARILY_LOST: last observed, NOT currently detected
        color, thickness = _COLOR_PERSON_LOST, 1
    if stale:
        color, thickness = _COLOR_STALE, 1
    cv2.rectangle(out, (x0, y0), (x1, y1), color, thickness)
    tag = {
        TrackLifecycle.CONFIRMED: "",
        TrackLifecycle.TENTATIVE: " T",
        TrackLifecycle.TEMPORARILY_LOST: " LOST",
    }[track.lifecycle]
    label = f"#{track.track_id} {track.confidence:.2f}{tag}"
    _draw_text(cv2, out, label, x0, max(0, y0 - 5), size=0.4, color=color)


def _draw_hand(
    cv2,
    out,
    raw: RawHand,
    stable: HandGesture | None,
    width: int,
    height: int,
    *,
    mirror: bool,
    stale: bool,
    now: float,
    frame_index: int,
    renderer: DiagnosticRenderer,
) -> None:
    landmarks = raw.landmarks
    if not landmarks:
        return
    pixels: dict[int, tuple[int, int]] = {}
    nonfinite = 0
    out_of_bounds = 0
    first_nonfinite: tuple[int, Landmark] | None = None
    first_oob: tuple[int, Landmark] | None = None
    for i, landmark in enumerate(landmarks):
        if not (math.isfinite(landmark.x) and math.isfinite(landmark.y)):
            nonfinite += 1
            if first_nonfinite is None:
                first_nonfinite = (i, landmark)
            continue
        px = hand_pixel(landmark.x, landmark.y, width, height, mirror=mirror)
        if px is None:
            out_of_bounds += 1
            if first_oob is None:
                first_oob = (i, landmark)
            continue
        pixels[i] = px
    if nonfinite:
        renderer.nonfinite_landmarks += nonfinite
        _log_landmark_anomaly(
            renderer,
            kind="non-finite hand landmark",
            counter_attr="nonfinite_landmarks",
            first=(first_nonfinite, nonfinite),
            first_logged_attr="_nonfinite_first_logged",
            last_logged_attr="_last_nonfinite_log",
            now=now,
            hand=raw,
            frame_index=frame_index,
        )
    if out_of_bounds:
        renderer.out_of_bounds_landmarks += out_of_bounds
        _log_landmark_anomaly(
            renderer,
            kind="out-of-bounds hand landmark",
            counter_attr="out_of_bounds_landmarks",
            first=(first_oob, out_of_bounds),
            first_logged_attr="_oob_first_logged",
            last_logged_attr="_last_oob_log",
            now=now,
            hand=raw,
            frame_index=frame_index,
        )
    edge_color = _COLOR_STALE if stale else _COLOR_HAND
    for a, b in HAND_EDGES:
        if a in pixels and b in pixels:
            cv2.line(out, pixels[a], pixels[b], edge_color, 1)
    point_color = _COLOR_STALE if stale else _COLOR_HAND
    for px in pixels.values():
        cv2.circle(out, px, 2, point_color, -1)
    wrist = pixels.get(0)
    if wrist is None:
        return  # no drawable anchor for the labels
    if stable is not None:
        _draw_text(cv2, out, stable_hand_label(stable), wrist[0], max(0, wrist[1] - 14), size=0.4, color=_COLOR_STABLE)
    _draw_text(cv2, out, raw_hand_label(raw), wrist[0], max(0, wrist[1] - 2), size=0.4, color=_COLOR_STALE if stale else _COLOR_RAW)


def _log_landmark_anomaly(
    renderer: DiagnosticRenderer,
    *,
    kind: str,
    counter_attr: str,
    first: tuple[tuple[int, Landmark] | None, int],
    first_logged_attr: str,
    last_logged_attr: str,
    now: float,
    hand: RawHand,
    frame_index: int,
) -> None:
    """First-occurrence detail, then a rate-limited summary (bounded output)."""
    first_sample, count = first
    first_logged = getattr(renderer, first_logged_attr)
    if not first_logged and first_sample is not None:
        setattr(renderer, first_logged_attr, True)
        i, lm = first_sample
        _LOGGER.warning(
            "%s skipped: frame=%d hand_idx=%d handedness=%s category=%s "
            "landmark=%d x=%r y=%r z=%r",
            kind,
            frame_index,
            hand.index,
            hand.handedness,
            hand.category,
            i,
            lm.x,
            lm.y,
            lm.z,
        )
        return
    last = getattr(renderer, last_logged_attr)
    if last is None or now - last >= _ANOMALY_LOG_INTERVAL_S:
        setattr(renderer, last_logged_attr, now)
        total = getattr(renderer, counter_attr)
        _LOGGER.warning(
            "%s: %d more (total %d, frame=%d)",
            kind,
            count,
            total,
            frame_index,
        )


def _matching_hand(hands: Sequence[HandGesture], raw_index: int, raw_hand_index: int) -> HandGesture | None:
    """The allowlisted gesture observation for a raw hand, if any."""
    for hand in hands:
        if hand.index == raw_hand_index:
            return hand
    return None


def _draw_evidence(cv2, out, snapshot: DiagnosticSnapshot, width: int, *, stale: bool) -> None:
    lines = [
        f"{state.kind}={state.value} {state.confidence:.2f}"
        + (f" [{state.track_id}]" if state.track_id else "")
        for state in snapshot.states
    ]
    if not lines:
        return
    color = _COLOR_STALE if stale else _COLOR_STABLE
    _draw_text_block(cv2, out, lines, x=6, y=14, size=0.4, color=color, align="topright", width=width)


def _draw_events(
    cv2,
    out,
    snapshot: DiagnosticSnapshot,
    now: float,
    ttl_s: float,
    width: int,
    *,
    stale: bool,
) -> None:
    events = snapshot.event_ttl_elapsed(now, ttl_s)
    if not events:
        return
    lines = [f"EVENT {event.event}" for event in events[:3]]
    color = _COLOR_STALE if stale else _COLOR_EVENT
    _draw_text_block(cv2, out, lines, x=6, y=14, size=0.4, color=color, align="bottomleft", width=width)


def _draw_text_block(cv2, out, lines: Sequence[str], *, x: int, y: int, size: float, color, align: str = "topleft", width: int = 0) -> None:
    height, _ = out.shape[:2]
    if align == "topright":
        y_start = y
        cursor = y_start
        for line in lines:
            tw, _ = cv2.getTextSize(line, _font(cv2), size, 1)[0]
            cv2.putText(out, line, (max(0, width - tw - x), cursor), _font(cv2), size, color, 1, cv2.LINE_AA)
            cursor += int(size * 18)
    elif align == "bottomleft":
        cursor = height - y
        for line in reversed(lines):
            cv2.putText(out, line, (x, cursor), _font(cv2), size, color, 1, cv2.LINE_AA)
            cursor -= int(size * 18)
    else:
        cursor = y
        for line in lines:
            cv2.putText(out, line, (x, cursor), _font(cv2), size, color, 1, cv2.LINE_AA)
            cursor += int(size * 18)


def _draw_text(cv2, out, text: str, x: int, y: int, *, size: float, color) -> None:
    cv2.putText(out, text, (x, y), _font(cv2), size, color, 1, cv2.LINE_AA)


def _font(cv2):
    return cv2.FONT_HERSHEY_SIMPLEX


def _fmt_fps(fps: float | None) -> str:
    return f"{fps:.1f}" if fps is not None else "n/a"


def _percentiles(values: Sequence[float]) -> tuple[float, float]:
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    return p50, p95
