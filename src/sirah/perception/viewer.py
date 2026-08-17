"""Diagnostic viewer: broker subscription -> renderer -> display backend.

The viewer is the async glue of M5.2B. It consumes a `CameraSource` that
is always a `FrameBroker` subscriber (the physical camera is owned exactly
once by the broker — the viewer never opens `/dev/videoN`), pulls the
newest frame at a bounded display rate, renders the latest
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
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from sirah.perception.contracts import CameraSource, Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.display import DisplayBackend
from sirah.perception.renderer import DiagnosticRenderer, RenderContext

_DEFAULT_DISPLAY_INTERVAL_S = 0.05  # ~20 fps display budget
_SNAPSHOT_WINDOW = 8


@dataclass
class ViewerStats:
    """Diagnostics for the display path itself."""

    displayed: int = 0
    dropped: int = 0
    display_fps: float | None = None

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
            self._render_and_show(frame, snapshot)
            self._stats.displayed += 1
            await asyncio.sleep(self._display_interval_s)

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
