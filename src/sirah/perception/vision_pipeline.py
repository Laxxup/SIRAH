"""Vision V1 (M8.1): reusable live perception → WorldState → AI context.

One component owns the physically-working stack — camera (via FrameBroker),
YuNet face, MediaPipe gesture and person workers, and the shared
EvidenceHub — and exposes the latest immutable `VisionContext` for the
conversation AI. It is the vertical slice between the existing perception
workers and the conversation context:

    camera
      → workers (face / gesture / person, off the event loop)
      → EvidenceHub (stable state + edge events)
      → PerceptionFacts → WorldState.perception
      → VisionContextProvider → compact AI context

The conversation never blocks perception and perception never waits for
the LLM: `vision_context()` is a synchronous read of the last snapshot.
If the pipeline cannot tick (camera failure), the provider's snapshot
lapses past its availability window and the AI simply proceeds without
visual grounding.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Self

from sirah.behavior.attention import AttentionManager
from sirah.behavior.contracts import AttentionSelector
from sirah.perception.contracts import (
    CameraSource,
    FaceDetector,
    Frame,
    GazeTarget,
    MultiFaceDetector,
)
from sirah.perception.evidence import EvidenceHub
from sirah.perception.fanout import FrameBroker
from sirah.perception.gesture import GESTURE_CONFIRM_WINDOW_S
from sirah.perception.gesture_worker import GestureTelemetry, GestureWorker
from sirah.perception.person import ObservedScene
from sirah.perception.person_worker import PersonDetectionWorker
from sirah.perception.vision_context import (
    VisionContextProvider,
    face_observation,
    person_observations,
)
from sirah.perception.world_state import PerceptionFacts, WorldState, WorldStateBuilder

_logger = logging.getLogger(__name__)


class VisionPipeline:
    """Owns the camera + perception workers and serves the vision context.

    `gesture_recognizer` and `person_detector` are optional adapter objects
    built by the caller (e.g. from verified local model paths); when omitted
    the corresponding worker is not started and the missing facts simply
    never enter the evidence layer (the AI still sees whatever the
    configured sensors provide). The shared evidence hub applies a
    gesture-specific confirmation window (see GESTURE_CONFIRM_WINDOW_S) so
    a held gesture confirms at realistic MediaPipe cadence without changing
    face/person policy; `gesture_observer` receives per-feed telemetry for
    physical latency diagnosis (opt-in, never enabled by default).
    """

    def __init__(
        self,
        *,
        camera: CameraSource,
        face_detector: FaceDetector,
        gesture_recognizer: object | None = None,
        person_detector: object | None = None,
        attention: AttentionSelector | None = None,
        clock: Callable[[], float] = time.monotonic,
        gesture_observer: Callable[[GestureTelemetry], None] | None = None,
    ) -> None:
        self._camera = camera
        self._face_detector = face_detector
        self._clock = clock
        self._attention = attention or AttentionManager()
        self._broker = FrameBroker(camera)
        self._face_camera = self._broker.subscribe()
        self._hub = EvidenceHub(
            kind_overrides={
                "gesture": {"confirm_window_s": GESTURE_CONFIRM_WINDOW_S}
            }
        )
        self._provider = VisionContextProvider(clock=clock)
        self._world = WorldStateBuilder()
        self._world_state: WorldState | None = None
        self._gesture_worker: GestureWorker | None = None
        self._person_worker: PersonDetectionWorker | None = None
        self._task: asyncio.Task[None] | None = None
        self._errors = 0
        self._degraded = False
        if gesture_recognizer is not None:
            self._gesture_worker = GestureWorker(
                self._broker.subscribe(),
                gesture_recognizer,
                evidence=self._hub,
                clock=clock,
                observer=gesture_observer,
            )
        if person_detector is not None:
            self._person_worker = PersonDetectionWorker(
                self._broker.subscribe(), person_detector, clock=clock
            )

    # -- public API ----------------------------------------------------

    @property
    def provider(self) -> VisionContextProvider:
        """The latest-snapshot store the conversation reads from."""
        return self._provider

    @property
    def world_state(self) -> WorldState | None:
        """Latest immutable WorldState (perception facts included)."""
        return self._world_state

    @property
    def errors(self) -> int:
        """Unexpected pipeline failures recorded so far."""
        return self._errors

    @property
    def degraded(self) -> bool:
        """True once a camera/detector failure interrupted the tick loop."""
        return self._degraded

    def vision_context(self) -> str | None:
        """Compact AI context for the current turn, or None when unavailable."""
        return self._provider.text()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._task is not None:
            return
        await self._broker.start()
        if self._gesture_worker is not None:
            await self._gesture_worker.start()
        if self._person_worker is not None:
            await self._person_worker.start()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._person_worker is not None:
            await self._person_worker.stop()
        if self._gesture_worker is not None:
            await self._gesture_worker.stop()
        await self._broker.stop()

    # -- internals -----------------------------------------------------

    async def _run(self) -> None:
        while True:
            try:
                frame = await self._face_camera.next_frame()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - camera failures degrade
                self._degrade(exc)
                return
            if frame is None:
                return  # EOF / broker stopped: hold the last snapshot
            try:
                self._tick(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - detector failures degrade
                self._degrade(exc)
                return

    def _tick(self, frame: Frame) -> None:
        now = self._clock()
        target = self._attended_target(frame)
        raws = [face_observation(target, now=now)]
        raws.extend(person_observations(self._person_scene(), now=now))
        snapshot = self._hub.observe(raws, now=now)
        facts = PerceptionFacts.from_snapshot(snapshot, observed_at=now)
        self._provider.observe(facts, snapshot.events, now=now)
        self._world.observe(target, now=now)
        self._world_state = self._world.snapshot(
            now=now,
            gaze_x=None,
            gaze_y=None,
            gaze_producer=None,
            vision_degraded=self._degraded,
            perception=facts,
        )

    def _attended_target(self, frame: Frame) -> GazeTarget | None:
        detector = self._face_detector
        if isinstance(detector, MultiFaceDetector):
            return self._attention.observe(detector.detect_many(frame))
        return detector.detect(frame)

    def _person_scene(self) -> ObservedScene | None:
        worker = self._person_worker
        return worker.last_scene if worker is not None else None

    def _degrade(self, exc: Exception) -> None:
        self._errors += 1
        self._degraded = True
        _logger.warning("vision pipeline degraded: %r", exc)