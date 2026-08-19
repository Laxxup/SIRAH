"""Gesture worker: run MediaPipe inference OFF the asyncio event loop.

The recognizer is a synchronous VIDEO-mode call. Running it directly in
the event loop would block SIRAH's runtime for ~10-30ms per frame, so a
dedicated worker owns a single worker thread and a FrameBroker
subscription:

- ONE executor with exactly one thread (never one thread per frame);
- exactly ONE inference in flight at a time; the loop awaits it, so no
  unbounded work queue can form;
- the broker's latest-frame slot is the only buffer: while inference
  runs, newer camera frames overwrite the slot, and the next iteration
  pulls the newest one (a slow detector skips intermediates — freshness
  > completeness is inherited from the broker, no MediaPipe-side
  dropping);
- absence semantics are VIDEO-mode's: an empty `hands` result means "no
  allowlisted hand" and advances the evidence layer's release/TTL
  directly; a dropped LIVE_STREAM callback can never be mistaken for
  "no hand" because LIVE_STREAM is not used.

The worker is intentionally isolated: a recognizer failure is recorded
and the worker keeps running (or stops cleanly), never raising into the
YuNet/preview pipeline. Closing the worker closes the recognizer and the
executor, and cancelling the run task does not leak anything.
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
from sirah.perception.evidence import (
    EvidenceHub,
    EvidenceSnapshot,
    PendingConfirmation,
)
from sirah.perception.gesture import (
    GESTURE_CONFIRM_WINDOW_S,
    GestureDetection,
    HandGesture,
    RawHand,
    gesture_observations,
)


@dataclass(frozen=True)
class GestureWorkerStats:
    """Aggregate gesture inference measurements for the preview/summary."""

    inferences: int
    errors: int
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


@dataclass(frozen=True)
class GestureTelemetry:
    """One gesture evidence feed, for physical latency diagnosis.

    Never carries landmarks or pixel frames — only the allowlisted
    gesture values, confidence and evidence state an operator needs to
    tell "slow inference" apart from "intermittent detection".
    """

    monotonic_s: float  # feed time (same clock as evidence ticks)
    inference_latency_ms: float  # MediaPipe call duration for this frame
    frame_age_ms: float | None  # feed time - camera capture time
    raw_gestures: tuple[tuple[str, float], ...]  # (value, confidence), allowlisted
    pending: tuple[PendingConfirmation, ...]  # in-acquisition gesture candidates
    stable: tuple[tuple[str, float], ...]  # (value, confidence) stable gestures
    events: tuple[str, ...]  # gesture evidence events emitted this feed


def _p50(values: Sequence[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _p95(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return round(ordered[index], 3)


class GestureWorker:
    """Consumes a CameraSource (typically a FrameBroker subscription) and
    feeds allowlisted gestures into an EvidenceHub on its own thread.

    `recognizer.recognize_detailed(frame)` runs on a single worker thread
    via `run_in_executor`; the event loop only awaits it. `last_detection`
    exposes the most recent full result (allowlisted hands + raw
    diagnostic hands) so the CLI preview can print what MediaPipe saw.
    """

    def __init__(
        self,
        camera: CameraSource,
        recognizer: object,
        *,
        evidence: EvidenceHub | None = None,
        clock: Callable[[], float] = time.monotonic,
        observer: Callable[[GestureTelemetry], None] | None = None,
    ) -> None:
        self._camera = camera
        self._recognizer = recognizer
        self._evidence = evidence or EvidenceHub(
            kind_overrides={
                "gesture": {"confirm_window_s": GESTURE_CONFIRM_WINDOW_S}
            }
        )
        self._clock = clock
        self._observer = observer
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._task: asyncio.Task[None] | None = None
        self._last_detection: GestureDetection | None = None
        self._latency_ms: list[float] = []
        self._frame_ages: list[float] = []
        self._emitted_events: list[str] = []
        self._inferences = 0
        self._errors = 0

    @property
    def evidence(self) -> EvidenceHub:
        return self._evidence

    @property
    def last_detection(self) -> GestureDetection | None:
        return self._last_detection

    @property
    def last_hands(self) -> tuple[HandGesture, ...]:
        detection = self._last_detection
        return detection.hands if detection is not None else ()

    @property
    def last_raw(self) -> tuple[RawHand, ...]:
        detection = self._last_detection
        return detection.raw if detection is not None else ()

    def stats(self) -> GestureWorkerStats:
        return GestureWorkerStats(
            inferences=self._inferences,
            errors=self._errors,
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
                max_workers=1, thread_name_prefix="sirah-gesture"
            )
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the loop, join the worker thread, close recognizer/executor.

        Cancelling `_run` interrupts the current `next_frame` wait (the
        broker's pump wakes waiters on stop) and the in-flight executor
        future; nothing is left running afterwards.
        """
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
        close = getattr(self._recognizer, "close", None)
        if callable(close):
            close()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            frame = await self._camera.next_frame()
            if frame is None:
                break
            detection, latency_ms = await loop.run_in_executor(
                self._executor, self._recognize, frame
            )
            self._feed(detection, frame, latency_ms)

    def _recognize(self, frame: Frame) -> tuple[GestureDetection, float]:
        started = self._clock()
        try:
            detection = self._recognizer.recognize_detailed(frame)  # type: ignore[attr-defined]
            latency_ms = (self._clock() - started) * 1000.0
            self._latency_ms.append(latency_ms)
            self._inferences += 1
            return detection, latency_ms
        except Exception:  # noqa: BLE001 - isolate the gesture subsystem
            self._errors += 1
            latency_ms = (self._clock() - started) * 1000.0
            self._latency_ms.append(latency_ms)
            return GestureDetection(hands=(), raw=(), timestamp_ms=0), latency_ms

    def _feed(self, detection: GestureDetection, frame: Frame, latency_ms: float) -> None:
        self._last_detection = detection
        now = self._clock()
        raws = gesture_observations(detection.hands, observed_at=now)
        snapshot = self._evidence.observe(raws, now=now)
        self._emitted_events.extend(snapshot.event_values())
        frame_age = now - frame.captured_at if frame.captured_at is not None else None
        if frame_age is not None:
            self._frame_ages.append(frame_age)
        self._emit_telemetry(detection, snapshot, now, latency_ms, frame_age)

    def _emit_telemetry(
        self,
        detection: GestureDetection,
        snapshot: EvidenceSnapshot,
        now: float,
        latency_ms: float,
        frame_age: float | None,
    ) -> None:
        """Deliver one feed's diagnosis to the observer (opt-in, no landmarks)."""
        if self._observer is None:
            return
        raw = tuple((hand.gesture, hand.confidence) for hand in detection.hands)
        pending = tuple(p for p in snapshot.pending if p.kind == "gesture")
        stable = tuple(
            (state.value, state.confidence)
            for state in snapshot.states
            if state.kind == "gesture"
        )
        events = tuple(
            event.event for event in snapshot.events if event.kind == "gesture"
        )
        self._observer(
            GestureTelemetry(
                monotonic_s=now,
                inference_latency_ms=latency_ms,
                frame_age_ms=frame_age,
                raw_gestures=raw,
                pending=pending,
                stable=stable,
                events=events,
            )
        )

    @property
    def emitted_events(self) -> tuple[str, ...]:
        """Edge events emitted by the evidence layer for gesture keys."""
        return tuple(self._emitted_events)
