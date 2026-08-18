"""sirah-perceive M6 person-worker integration tests: person tracks are
snapshotted per tick, temporally aligned with the displayed frame, and the
worker lifecycle is clean — over fakes, no model, camera or hardware."""

from __future__ import annotations

from dataclasses import dataclass

from sirah.behavior.attention import AttentionManager
from sirah.cli.perceive import perceive_gesture_preview, perceive_preview
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.evidence import EvidenceHub
from sirah.perception.person import PersonTrack, TrackLifecycle
from sirah.perception.person_worker import PersonWorkerStats


class FakeCamera:
    def __init__(self, frames: list[tuple[int, float]]) -> None:
        self._frames = iter(frames)
        self.stopped = False

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        try:
            index, captured_at = next(self._frames)
        except StopIteration:
            return None
        return Frame(index=index, payload=None, captured_at=captured_at)

    async def stop(self) -> None:
        self.stopped = True


class EmptyFaceDetector:
    def detect(self, frame: Frame) -> GazeTarget | None:
        return None


def _track(track_id: int, lifecycle: TrackLifecycle = TrackLifecycle.CONFIRMED) -> PersonTrack:
    return PersonTrack(
        track_id=track_id,
        lifecycle=lifecycle,
        x=0.4,
        y=0.3,
        width=0.3,
        height=0.5,
        confidence=0.9,
        first_seen=0.0,
        last_seen=0.1,
        last_source_frame_index=3,
    )


@dataclass
class FakePersonWorker:
    """Mimics PersonDetectionWorker's async + temporal-alignment surface."""

    scene_source_frame: int
    started: bool = False
    stopped: bool = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def scene_for(self, frame_index: int) -> object | None:
        # the worker's scene is only valid for frames not older than its source
        if frame_index < self.scene_source_frame:
            return None
        return _FakeScene(self.scene_source_frame)

    def stats(self) -> PersonWorkerStats:
        return PersonWorkerStats(
            inferences=5, errors=0, detections=6, expirations=0, stale_updates=0
        )


@dataclass(frozen=True)
class _FakeScene:
    source_frame_index: int

    @property
    def tracks(self):
        return (_track(7),)


def _advancing_clock():
    state = {"t": -0.1}

    def clock() -> float:
        state["t"] += 0.1
        return state["t"]

    return clock


async def test_preview_snapshots_aligned_person_tracks():
    camera = FakeCamera([(0, 0.0), (1, 0.1), (2, 0.2), (3, 0.3)])
    worker = FakePersonWorker(scene_source_frame=3)
    summary = await perceive_preview(
        camera,
        EmptyFaceDetector(),
        max_frames=4,
        clock=_advancing_clock(),
        attention=AttentionManager(),
        evidence=EvidenceHub(),
        person_worker=worker,
    )
    # frames 0-2 come before the scene's source frame: no tracks leaked
    assert [obs.person_tracks for obs in summary.observations[:3]] == [(), (), ()]
    # frame 3 matches the scene source: tracks appear
    assert len(summary.observations[3].person_tracks) == 1
    assert summary.observations[3].person_tracks[0].track_id == 7
    assert worker.started and worker.stopped
    assert camera.stopped
    assert summary.person_inferences == 5


async def test_preview_tracks_all_scenes_for_older_source():
    """A scene produced at frame 1 is valid for frames 1..N (not newer)."""
    camera = FakeCamera([(0, 0.0), (1, 0.1), (2, 0.2)])
    worker = FakePersonWorker(scene_source_frame=1)
    summary = await perceive_preview(
        camera,
        EmptyFaceDetector(),
        max_frames=3,
        clock=_advancing_clock(),
        attention=AttentionManager(),
        evidence=EvidenceHub(),
        person_worker=worker,
    )
    assert summary.observations[0].person_tracks == ()
    assert len(summary.observations[1].person_tracks) == 1
    assert len(summary.observations[2].person_tracks) == 1


async def test_gesture_preview_snapshots_person_tracks():
    camera = FakeCamera([(0, 0.0), (1, 0.1), (2, 0.2)])
    worker = FakePersonWorker(scene_source_frame=2)

    class FakeGestureWorker:
        def __init__(self) -> None:
            self._ev = []

        async def start(self) -> None:
            return None

        async def stop(self) -> None:
            return None

        @property
        def last_raw(self):
            return ()

        @property
        def last_hands(self):
            return ()

        @property
        def emitted_events(self):
            return tuple(self._ev)

        def stats(self):
            from sirah.perception.gesture_worker import GestureWorkerStats

            return GestureWorkerStats(inferences=0, errors=0)

    summary = await perceive_gesture_preview(
        camera,
        EmptyFaceDetector(),
        gesture_worker=FakeGestureWorker(),
        max_frames=3,
        clock=_advancing_clock(),
        attention=AttentionManager(),
        evidence=EvidenceHub(),
        person_worker=worker,
    )
    assert summary.observations[0].person_tracks == ()
    assert summary.observations[1].person_tracks == ()
    assert len(summary.observations[2].person_tracks) == 1