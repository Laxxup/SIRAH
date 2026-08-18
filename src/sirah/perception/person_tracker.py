"""Greedy IoU person tracker (M6): ByteTrack-style, pure Python.

Association follows ByteTrack's BYTE idea — every detection is valuable:

- stage 1: high-confidence detections match existing tracks (greedy IoU,
  descending confidence, deterministic tie-break by ascending track_id);
- stage 2: low-confidence detections recover still-unmatched tracks
  (a briefly-occluded or partially-visible person is often detected with
  low confidence just before/after the miss);
- unmatched high detections spawn tentative tracks (confirmed after
  `confirm_frames` consecutive hits);
- confirmed/tentative tracks missed by both stages become
  TEMPORARILY_LOST for up to `track_buffer_seconds` of MONOTONIC wall
  time since their last observation, then EXPIRED and dropped. Time is
  used (not camera-frame deltas) so the "recently observed" window does
  not stretch when the camera/detector runs at a different effective
  rate: the same physical occlusion expires after the same wall duration
  at 10 Hz, 20 Hz or 30 Hz;
- velocity is a smoothed normalized-units-per-second box-center estimate.

Properties that matter for M6:

- zero dependencies, deterministic, fully unit-testable (no RNG);
- greedy matching is sufficient for ≤ tens of boxes (Hungarian not needed);
- no ReID: `track_id` is a session-local trajectory label and MAY switch
  after severe occlusion/crossing — the scene never claims identity;
- pure normalized-box math, so it runs on x86 and Raspberry Pi alike.

Semantics: TEMPORARILY_LOST tracks keep their LAST OBSERVED bbox. That is
"recently observed at X" — consumers must render it distinctly and never
treat it as "still at X" (freshness is the scene's job, see ObservedScene).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sirah.perception.person import (
    PersonDetection,
    PersonTrack,
    TrackLifecycle,
)


def _iou(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> float:
    """Intersection over union of two normalized boxes (pure math).

    Boxes are clamped to the [0, 1] frame for the comparison so a person
    spilling a few pixels past the edge still matches itself; core box
    values are never modified, only the similarity metric clips.
    """
    ix0 = max(ax, bx)
    iy0 = max(ay, by)
    ix1 = min(ax + aw, bx + bw)
    iy1 = min(ay + ah, by + bh)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _InternalTrack:
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
    detector: str
    hit_streak: int
    lost_seconds: float
    velocity: tuple[float, float] | None
    prev_center: tuple[float, float] | None = None
    prev_time: float | None = None


class GreedyIoUTracker:
    """Deterministic ByteTrack-style greedy IoU tracker (M6 baseline)."""

    def __init__(
        self,
        *,
        track_thresh: float = 0.5,
        low_thresh: float = 0.25,
        match_thresh: float = 0.4,
        track_buffer_seconds: float = 2.0,
        confirm_frames: int = 2,
        velocity_smoothing: float = 0.5,
    ) -> None:
        if not 0.0 < low_thresh <= track_thresh <= 1.0:
            raise ValueError("require 0 < low_thresh <= track_thresh <= 1")
        if not 0.0 <= match_thresh <= 1.0:
            raise ValueError("match_thresh must be normalized")
        if track_buffer_seconds <= 0:
            raise ValueError("track_buffer_seconds must be positive")
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be positive")
        if not 0.0 < velocity_smoothing <= 1.0:
            raise ValueError("velocity_smoothing must be in (0, 1]")
        self.track_thresh = track_thresh
        self.low_thresh = low_thresh
        self.match_thresh = match_thresh
        self.track_buffer_seconds = track_buffer_seconds
        self.confirm_frames = confirm_frames
        self.velocity_smoothing = velocity_smoothing
        self._tracks: list[_InternalTrack] = []
        self._next_id = 0
        self._last_frame_index = -1
        self._stale_updates = 0
        self._expirations = 0
        self._spawns = 0

    # -- public API ----------------------------------------------------

    def update(
        self,
        detections: Sequence[PersonDetection],
        *,
        source_frame_index: int,
        now: float,
    ) -> tuple[PersonTrack, ...]:
        """Advance the tracker with ONE frame's detections.

        Out-of-order / repeated frame indices are ignored (a defensive
        guard: a stale update must never corrupt newer track state); the
        currently-known tracks are returned unchanged. `now` is the
        monotonic assembly time used only for output freshness.
        """
        if source_frame_index < 0:
            raise ValueError("source_frame_index must not be negative")
        if source_frame_index <= self._last_frame_index:
            self._stale_updates += 1
            return self._snapshot(now)
        self._last_frame_index = source_frame_index

        high = [
            d for d in detections if d.confidence >= self.track_thresh
        ]
        low = [
            d for d in detections
            if self.low_thresh <= d.confidence < self.track_thresh
        ]
        matched_ids: set[int] = set()
        matched: set[PersonDetection] = set()

        for det in sorted(high, key=lambda d: d.confidence, reverse=True):
            best = self._best_match(det, matched_ids)
            if best is not None:
                matched_ids.add(best.track_id)
                matched.add(det)
                self._apply_match(best, det, source_frame_index)
        for det in sorted(low, key=lambda d: d.confidence, reverse=True):
            best = self._best_match(det, matched_ids)
            if best is not None:
                matched_ids.add(best.track_id)
                matched.add(det)
                self._apply_match(best, det, source_frame_index)

        for track in self._tracks:
            if track.track_id not in matched_ids:
                self._mark_miss(track, now)

        for det in high:
            if det not in matched:
                self._spawn(det, source_frame_index)

        self._expire()
        return self._snapshot(now)

    @property
    def stale_updates(self) -> int:
        """Defensive counter: out-of-order updates ignored so far."""
        return self._stale_updates

    @property
    def expirations(self) -> int:
        """Tracks expired (lost longer than the buffer) so far."""
        return self._expirations

    @property
    def spawns(self) -> int:
        """Tracks created so far (tentative births)."""
        return self._spawns

    # -- internals -----------------------------------------------------

    def _active_candidates(self, matched_ids: set[int]) -> list[_InternalTrack]:
        return [
            track
            for track in self._tracks
            if track.track_id not in matched_ids
            and track.lifecycle is not TrackLifecycle.EXPIRED
        ]

    def _best_match(
        self, det: PersonDetection, matched_ids: set[int]
    ) -> _InternalTrack | None:
        best: _InternalTrack | None = None
        best_iou = self.match_thresh
        for track in self._active_candidates(matched_ids):
            iou = _iou(
                det.x, det.y, det.width, det.height,
                track.x, track.y, track.width, track.height,
            )
            if iou > best_iou or (
                iou == best_iou and best is not None and track.track_id < best.track_id
            ):
                best = track
                best_iou = iou
        return best if best_iou >= self.match_thresh else None

    def _apply_match(
        self, track: _InternalTrack, det: PersonDetection, source_frame_index: int
    ) -> None:
        cx, cy = det.center
        if track.prev_center is not None and track.prev_time is not None:
            dt = det.produced_at - track.prev_time
            if dt > 0:
                vx = (cx - track.prev_center[0]) / dt
                vy = (cy - track.prev_center[1]) / dt
                if track.velocity is None:
                    track.velocity = (vx, vy)
                else:
                    a = self.velocity_smoothing
                    track.velocity = (
                        a * vx + (1.0 - a) * track.velocity[0],
                        a * vy + (1.0 - a) * track.velocity[1],
                    )
        track.prev_center = (cx, cy)
        track.prev_time = det.produced_at
        track.x, track.y = det.x, det.y
        track.width, track.height = det.width, det.height
        track.confidence = det.confidence
        track.last_seen = det.produced_at
        track.last_source_frame_index = source_frame_index
        track.lost_seconds = 0.0
        track.hit_streak += 1
        if track.lifecycle is TrackLifecycle.TEMPORARILY_LOST or (
            track.lifecycle is TrackLifecycle.TENTATIVE
            and track.hit_streak >= self.confirm_frames
        ):
            track.lifecycle = TrackLifecycle.CONFIRMED

    def _mark_miss(self, track: _InternalTrack, now: float) -> None:
        if track.lifecycle is TrackLifecycle.TENTATIVE:
            # never confirmed: it was noise; drop it, do not keep it "lost"
            track.lifecycle = TrackLifecycle.EXPIRED
            return
        # monotonic wall time since the person was last observed: the
        # "recently observed" window is a real duration, independent of
        # the camera/detector effective rate
        track.lost_seconds = max(0.0, now - track.last_seen)
        if track.lifecycle is TrackLifecycle.CONFIRMED:
            track.lifecycle = TrackLifecycle.TEMPORARILY_LOST

    def _spawn(self, det: PersonDetection, source_frame_index: int) -> None:
        cx, cy = det.center
        track = _InternalTrack(
            track_id=self._next_id,
            lifecycle=TrackLifecycle.TENTATIVE,
            x=det.x,
            y=det.y,
            width=det.width,
            height=det.height,
            confidence=det.confidence,
            first_seen=det.produced_at,
            last_seen=det.produced_at,
            last_source_frame_index=source_frame_index,
            detector=det.detector,
            hit_streak=1,
            lost_seconds=0.0,
            velocity=None,
            prev_center=(cx, cy),
            prev_time=det.produced_at,
        )
        self._next_id += 1
        self._spawns += 1
        self._tracks.append(track)

    def _expire(self) -> None:
        keep: list[_InternalTrack] = []
        for track in self._tracks:
            if (
                track.lifecycle is TrackLifecycle.TEMPORARILY_LOST
                and track.lost_seconds >= self.track_buffer_seconds
            ):
                track.lifecycle = TrackLifecycle.EXPIRED
                self._expirations += 1
            if track.lifecycle is TrackLifecycle.EXPIRED:
                continue
            keep.append(track)
        self._tracks = keep

    def _snapshot(self, now: float) -> tuple[PersonTrack, ...]:
        order = {
            TrackLifecycle.CONFIRMED: 0,
            TrackLifecycle.TENTATIVE: 1,
            TrackLifecycle.TEMPORARILY_LOST: 2,
        }
        live = [
            track for track in self._tracks
            if track.lifecycle is not TrackLifecycle.EXPIRED
        ]
        live.sort(key=lambda t: (order[t.lifecycle], t.track_id))
        return tuple(
            PersonTrack(
                track_id=track.track_id,
                lifecycle=track.lifecycle,
                x=track.x,
                y=track.y,
                width=track.width,
                height=track.height,
                confidence=track.confidence,
                first_seen=track.first_seen,
                last_seen=track.last_seen,
                last_source_frame_index=track.last_source_frame_index,
                detector=track.detector,
                velocity=track.velocity,
            )
            for track in live
        )