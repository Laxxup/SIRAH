"""Deterministic diagnostic renderer (M5.2B).

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
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sirah.perception.contracts import Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.gesture import HandGesture, RawHand

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


def raw_hand_label(raw: RawHand) -> str:
    """Presentation label for raw perception: MediaPipe-reported data."""
    return f"{raw.handedness.lower()} hand {raw.category} {raw.confidence:.2f}"


def stable_hand_label(hand: HandGesture) -> str:
    """Presentation label for an allowlisted gesture observation."""
    return f"{hand.gesture} {hand.confidence:.2f} ({hand.handedness} hand)"


class DiagnosticRenderer:
    """Pure renderer: (Frame, DiagnosticSnapshot | None) -> annotated BGR copy."""

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
) -> None:
    for face in snapshot.faces:
        _draw_face(cv2, out, face, width, height, mirror=mirror, stale=stale)
    for index, raw in enumerate(snapshot.raw_hands):
        stable = _matching_hand(snapshot.hands, index, raw.index)
        _draw_hand(cv2, out, raw, stable, width, height, mirror=mirror, stale=stale)
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
) -> None:
    landmarks = raw.landmarks
    if not landmarks:
        return
    edge_color = _COLOR_STALE if stale else _COLOR_HAND
    for a, b in HAND_EDGES:
        if a >= len(landmarks) or b >= len(landmarks):
            continue
        ax, ay = project_x(landmarks[a].x, width, mirror=mirror), project_y(landmarks[a].y, height)
        bx, by = project_x(landmarks[b].x, width, mirror=mirror), project_y(landmarks[b].y, height)
        cv2.line(out, (ax, ay), (bx, by), edge_color, 1)
    for point in landmarks:
        px, py = project_x(point.x, width, mirror=mirror), project_y(point.y, height)
        cv2.circle(out, (px, py), 2, _COLOR_STALE if stale else _COLOR_HAND, -1)
    wrist = landmarks[0]
    wx = project_x(wrist.x, width, mirror=mirror)
    wy = project_y(wrist.y, height)
    if stable is not None:
        _draw_text(cv2, out, stable_hand_label(stable), wx, max(0, wy - 14), size=0.4, color=_COLOR_STABLE)
    _draw_text(cv2, out, raw_hand_label(raw), wx, max(0, wy - 2), size=0.4, color=_COLOR_STALE if stale else _COLOR_RAW)


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
