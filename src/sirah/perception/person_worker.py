"""Person worker (M6): run person detection+tracking OFF the event loop.

Mirrors `GestureWorker`'s isolation contract exactly:

- ONE executor with exactly one thread (never one per frame);
- exactly ONE detection in flight at a time; the loop awaits it, so no
  unbounded work queue can form;
- the FrameBroker's latest-frame slot is the only buffer: while inference
  runs, newer camera frames overwrite the slot and the next iteration
  pulls the newest one (a slow ~20 Hz detector drops intermediates —
  freshness > completeness inherited from the broker);
- the tracker is advanced ONLY with the frame the detector actually
  processed, so track state is frame-consistent by construction;
- failure containment: a detector/tracker exception is recorded
  (person errors) and the LAST valid scene stays exposed — never a
  fabricated or partial observation — and never raises into the YuNet/
  preview pipeline;
- clean shutdown: cancelling the run task wakes the pending
  `next_frame` wait, the executor joins, and the detector is closed.

Temporal provenance: `scene_for(frame_index)` is the ONLY way consumers
read the scene; it returns the latest scene whose `source_frame_index` is
not newer than the frame being described, so a newer detection is never
painted onto an older frame.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Self

from sirah.perception.contracts import CameraSource, Frame
from sirah.perception.person import ObservedScene, PersonTrack
from sirah.perception.person_tracker import GreedyIoUTracker


@dataclass(frozen=True)
class PersonWorkerStats:
    """Aggregate person detection/tracking measurements."""

    inferences: int
    errors: int
    detections: int
    expirations: int
    stale_updates: int
    latency_ms: tuple[float, ...] = ()
    frame_age_s: tuple[float, ...] = ()

    @property
    def latency_p50(self) -> float | None:
        return _p50(self.latency_ms)

    @property
    def latency_p95(self) -> float | None:
        return _p95(self.latency_ms)

    @property
    def frame_age_p50(self) -> float | None:
        return _p50(self.frame_age_s)

    @property
    def frame_age_p95(self) -> float | None:
        return _p95(self.frame_age_s)


def _p50(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _p95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return round(ordered[index], 3)


class PersonDetectionWorker:
    """Consumes a CameraSource (FrameBroker subscription) and produces the
    latest temporally-consistent ObservedScene on its own worker thread.

    Detection and tracking run together on the single worker thread so
    track state is updated exactly once per processed frame, off the
    asyncio event loop.
    """

    def __init__(
        self,
        camera: CameraSource,
        detector: object,
        *,
        tracker: GreedyIoUTracker | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._camera = camera
        self._detector = detector
        self._tracker = tracker or GreedyIoUTracker()
        self._clock = clock
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._task: asyncio.Task[None] | None = None
        self._last_scene: ObservedScene | None = None
        self._latency_ms: list[float] = []
        self._frame_ages: list[float] = []
        self._inferences = 0
        self._errors = 0
        self._detections = 0

    @property
    def last_scene(self) -> ObservedScene | None:
        return self._last_scene

    @property
    def last_tracks(self) -> tuple[PersonTrack, ...]:
        scene = self._last_scene
        return scene.tracks if scene is not None else ()

    def scene_for(self, frame_index: int) -> ObservedScene | None:
        """The latest scene that describes `frame_index` or an older frame.

        This is the temporal-provenance gate: a scene produced from a
        NEWER source frame is never handed out for an older displayed
        frame, so detections cannot be painted ahead of the camera.
        """
        scene = self._last_scene
        if scene is None or scene.source_frame_index > frame_index:
            return None
        return scene

    def stats(self) -> PersonWorkerStats:
        return PersonWorkerStats(
            inferences=self._inferences,
            errors=self._errors,
            detections=self._detections,
            expirations=self._tracker.expirations,
            stale_updates=self._tracker.stale_updates,
            latency_ms=tuple(self._latency_ms),
            frame_age_s=tuple(self._frame_ages),
        )

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="sirah-person"
            )
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the loop, join the worker thread, close detector/executor."""
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        executor = self._executor
        self._executor = None
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        close = getattr(self._detector, "close", None)
        if callable(close):
            close()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            frame = await self._camera.next_frame()
            if frame is None:
                break
            scene = await loop.run_in_executor(
                self._executor, self._process, frame
            )
            self._store(scene, frame)

    def _process(self, frame: Frame) -> ObservedScene | None:
        started = self._clock()
        try:
            detections = self._detector.detect_persons(frame)  # type: ignore[attr-defined]
            now = self._clock()
            tracks = self._tracker.update(
                detections, source_frame_index=frame.index, now=now
            )
            self._latency_ms.append((self._clock() - started) * 1000.0)
            self._inferences += 1
            self._detections += len(detections)
            return ObservedScene(
                tracks=tracks,
                observed_at=now,
                source_frame_index=frame.index,
            )
        except Exception:  # noqa: BLE001 - isolate the person subsystem
            self._errors += 1
            self._latency_ms.append((self._clock() - started) * 1000.0)
            return None

    def _store(self, scene: ObservedScene | None, frame: Frame) -> None:
        if scene is None:
            return
        self._last_scene = scene
        if frame.captured_at is not None:
            self._frame_ages.append(scene.observed_at - frame.captured_at)