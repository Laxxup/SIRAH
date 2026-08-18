"""Diagnostic viewer: broker subscription -> renderer -> display backend.

The viewer is the async glue of M5.2B/5.2C. It consumes a `CameraSource`
that is always a `FrameBroker` subscriber (the physical camera is owned
exactly once by the broker — the viewer never opens `/dev/videoN`), pulls
the newest frame at a bounded display rate, renders the latest
`DiagnosticSnapshot` on a private copy and hands the result to the
`DisplayBackend`.

Temporal correspondence is explicit and bounded:

- the perceive loop calls `push(snapshot)` per processed frame; the
  viewer keeps a small sliding window keyed by frame index;
- when rendering a displayed frame N, it uses the newest snapshot whose
  frame_index <= N, so it never paints detections from a *newer* frame
  onto an *older* displayed frame, and
- the renderer independently drops overlays older than its drop window
  and dims stale ones, so staleness is never silent.

Backpressure: the display loop sleeps at most `display_interval_s` between
frames and the backend keeps exactly one latest-frame slot, so a slow
display drops intermediate frames instead of queueing them (freshness >
completeness). `user_closed` is surfaced to the perceive loop so q/Esc on
the ffplay window shuts the whole preview down cleanly.

Failure containment (M5.2C): an unexpected renderer exception must never
kill the camera/broker/worker pipeline. The display loop increments
`render_errors`, logs the first occurrence (then rate-limits), falls back
to showing a plain unannotated copy of the frame so the camera image never
freezes, and keeps running. Cancellation is never swallowed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from sirah.perception.contracts import CameraSource, Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.display import DisplayBackend
from sirah.perception.renderer import DiagnosticRenderer, RenderContext

_LOGGER = logging.getLogger(__name__)

_DEFAULT_DISPLAY_INTERVAL_S = 0.05  # ~20 fps display budget
_SNAPSHOT_WINDOW = 8
_RENDER_ERROR_LOG_INTERVAL_S = 5.0


@dataclass
class ViewerStats:
    """Diagnostics for the display path itself."""

    displayed: int = 0
    dropped: int = 0
    display_fps: float | None = None
    render_errors: int = 0
    out_of_bounds_landmarks: int = 0
    nonfinite_landmarks: int = 0

    @property
    def frames(self) -> int:
        return self.displayed


class DiagnosticViewer:
    """Owns the display loop: frame subscription -> render -> backend.show.

    `camera` is the broker subscription this viewer consumes (never the
    physical source). Snapshots are pushed from the perceive loop via
    `push`; the renderer projects normalized overlays onto whichever
    frame the display loop is showing.
    """

    def __init__(
        self,
        camera: CameraSource,
        renderer: DiagnosticRenderer,
        backend: DisplayBackend,
        *,
        display_interval_s: float = _DEFAULT_DISPLAY_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if display_interval_s <= 0:
            raise ValueError("display_interval_s must be positive")
        self._camera = camera
        self._renderer = renderer
        self._backend = backend
        self._display_interval_s = display_interval_s
        self._clock = clock
        self._snapshots: deque[DiagnosticSnapshot] = deque(maxlen=_SNAPSHOT_WINDOW)
        self._latest_index: int | None = None
        self._task: asyncio.Task[None] | None = None
        self._stats = ViewerStats()
        self._mirror = False
        self._frame_times: deque[float] = deque()
        self._render_error_first_logged = False
        self._last_render_error_log: float | None = None

    @property
    def stats(self) -> ViewerStats:
        return self._stats

    @property
    def user_closed(self) -> bool:
        return self._backend.user_closed

    @property
    def mirror(self) -> bool:
        return self._mirror

    def set_mirror(self, mirror: bool) -> None:
        """Presentation-only horizontal flip (rendering transform only)."""
        self._mirror = bool(mirror)

    def push(self, snapshot: DiagnosticSnapshot) -> None:
        """Record one perceive-loop snapshot (latest-frame window)."""
        self._snapshots.append(snapshot)
        self._latest_index = snapshot.frame_index

    def clear(self) -> None:
        """Drop all retained snapshots (e.g. after a reset)."""
        self._snapshots.clear()
        self._latest_index = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the display loop and close the backend (idempotent)."""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._backend.close()

    async def _run(self) -> None:
        while True:
            frame = await self._camera.next_frame()
            if frame is None:
                break
            if self._backend.user_closed:
                break
            snapshot = self._best_snapshot(frame.index)
            try:
                self._render_and_show(frame, snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - viewer failure boundary
                # Unexpected rendering failure: keep perception alive. Show a
                # plain unannotated copy so the camera image never freezes.
                self._stats.render_errors += 1
                self._log_render_error(exc, frame.index)
                fallback = _plain_copy(frame)
                if fallback is not None:
                    self._backend.show(fallback)
            else:
                self._stats.displayed += 1
            self._sync_anomaly_stats()
            await asyncio.sleep(self._display_interval_s)

    def _sync_anomaly_stats(self) -> None:
        self._stats.out_of_bounds_landmarks = self._renderer.out_of_bounds_landmarks
        self._stats.nonfinite_landmarks = self._renderer.nonfinite_landmarks

    def _log_render_error(self, exc: Exception, frame_index: int) -> None:
        now = self._clock()
        if not self._render_error_first_logged:
            self._render_error_first_logged = True
            _LOGGER.error(
                "viewer render failed (degrading to raw frame): frame=%d exc=%s: %s",
                frame_index,
                type(exc).__name__,
                exc,
            )
            return
        last = self._last_render_error_log
        if last is None or now - last >= _RENDER_ERROR_LOG_INTERVAL_S:
            self._last_render_error_log = now
            _LOGGER.error(
                "viewer render failures: %d total (last at frame=%d): %s: %s",
                self._stats.render_errors,
                frame_index,
                type(exc).__name__,
                exc,
            )

    def _render_and_show(self, frame: Frame, snapshot: DiagnosticSnapshot | None) -> None:
        now = self._clock()
        self._tick_display_fps(now)
        context = RenderContext(
            now=now, mirror=self._mirror, display_fps=self._stats.display_fps
        )
        rendered = self._renderer.render(frame, snapshot, context)
        self._backend.show(rendered)

    def _best_snapshot(self, frame_index: int) -> DiagnosticSnapshot | None:
        """Newest snapshot whose frame_index is not newer than `frame_index`."""
        for snapshot in reversed(self._snapshots):
            if snapshot.frame_index <= frame_index:
                return snapshot
        return None

    def _tick_display_fps(self, now: float) -> None:
        self._frame_times.append(now)
        window = 1.0
        while self._frame_times and now - self._frame_times[0] > window:
            self._frame_times.popleft()
        if len(self._frame_times) >= 2:
            span = self._frame_times[-1] - self._frame_times[0]
            if span > 0:
                self._stats.display_fps = (len(self._frame_times) - 1) / span


def _plain_copy(frame: Frame) -> object | None:
    """A safe unannotated copy of the frame for viewer degradation.

    Returns None when the payload is not an ndarray image so the viewer
    simply skips showing rather than freezing or crashing.
    """
    import numpy as np

    payload = frame.payload
    if payload is None or not isinstance(payload, np.ndarray) or payload.ndim < 2:
        return None
    return np.array(payload, copy=True)
