"""DiagnosticViewer tests (M5.2B): temporal correspondence, latest-frame
display semantics, user_closed propagation and clean teardown. Uses fakes
for the camera source, renderer and backend — no display server needed.

M5.2C adds: unexpected renderer exceptions must not kill the pipeline —
the viewer increments `render_errors`, shows a plain copy of the frame,
and keeps rendering subsequent frames.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np

from sirah.perception.contracts import CameraSource, Frame
from sirah.perception.diagnostic import DiagnosticSnapshot
from sirah.perception.display import DisplayBackend
from sirah.perception.gesture import Landmark, RawHand
from sirah.perception.renderer import DiagnosticRenderer
from sirah.perception.viewer import DiagnosticViewer, ViewerStats


class FakeBackend(DisplayBackend):
    def __init__(self) -> None:
        self.frames: list[object] = []
        self._user_closed = False
        self.closed = False

    def show(self, frame: object) -> None:
        self.frames.append(frame)

    @property
    def user_closed(self) -> bool:
        return self._user_closed

    def set_user_closed(self, value: bool) -> None:
        self._user_closed = value

    def close(self) -> None:
        self.closed = True


class FakeCamera(CameraSource):
    def __init__(self, frames: list[Frame]) -> None:
        self._frames = iter(frames)

    async def start(self) -> None:
        pass

    async def next_frame(self) -> Frame | None:
        try:
            return next(self._frames)
        except StopIteration:
            return None

    async def stop(self) -> None:
        pass


class RecordingRenderer(DiagnosticRenderer):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[int, int | None]] = []

    def render(self, frame, snapshot, context):
        self.seen.append((frame.index, snapshot.frame_index if snapshot else None))
        return frame.payload


def _snap(frame_index: int, created_at: float = 10.0) -> DiagnosticSnapshot:
    return DiagnosticSnapshot(
        frame_index=frame_index,
        created_at=created_at,
        captured_at=created_at,
    )


def test_viewer_uses_newest_snapshot_not_newer_than_displayed_frame():
    renderer = RecordingRenderer()
    backend = FakeBackend()
    camera = FakeCamera(
        [Frame(index=1, payload=None, captured_at=1.0), Frame(index=2, payload=None, captured_at=2.0)]
    )
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    viewer.push(_snap(1))  # snapshot for frame 1
    viewer.push(_snap(2))  # snapshot for frame 2 arrives before display
    viewer.push(_snap(3))  # snapshot for a FUTURE frame
    asyncio.run(_run_until(viewer, 2))
    assert renderer.seen[0] == (1, 1)  # never paint frame-3 detections on frame 1
    assert renderer.seen[1] == (2, 2)


def test_viewer_uses_last_snapshot_when_none_newer():
    renderer = RecordingRenderer()
    backend = FakeBackend()
    camera = FakeCamera(
        [Frame(index=5, payload=None, captured_at=5.0), Frame(index=6, payload=None, captured_at=6.0)]
    )
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    viewer.push(_snap(4))
    viewer.push(_snap(6))  # this is NOT newer than frame 6
    asyncio.run(_run_until(viewer, 2))
    assert renderer.seen[0] == (5, 4)
    assert renderer.seen[1] == (6, 6)


def test_viewer_renders_none_when_no_snapshot_fits():
    renderer = RecordingRenderer()
    backend = FakeBackend()
    camera = FakeCamera([Frame(index=1, payload=None, captured_at=1.0)])
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    asyncio.run(_run_until(viewer, 1))
    assert renderer.seen[0] == (1, None)


def test_viewer_stops_when_backend_reports_user_closed():
    renderer = RecordingRenderer()
    backend = FakeBackend()
    camera = FakeCamera(
        [Frame(index=1, payload=None, captured_at=1.0), Frame(index=2, payload=None, captured_at=2.0)]
    )
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    backend.set_user_closed(True)
    asyncio.run(_run_until(viewer, 10))
    assert len(renderer.seen) == 0  # stopped before rendering anything


def test_viewer_surfaces_user_closed():
    backend = FakeBackend()
    backend.set_user_closed(True)
    camera = FakeCamera([])
    viewer = DiagnosticViewer(camera, RecordingRenderer(), backend)
    assert viewer.user_closed is True


def test_viewer_set_mirror_reflects_in_context():
    backend = FakeBackend()
    renderer = _MirrorRecordingRenderer()
    camera = FakeCamera([Frame(index=1, payload=None, captured_at=1.0)])
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    viewer.set_mirror(True)
    viewer.push(_snap(1))
    asyncio.run(_run_until(viewer, 1))
    assert renderer.mirror_seen is True


def test_viewer_stats_track_displayed_frames():
    backend = FakeBackend()
    renderer = RecordingRenderer()
    camera = FakeCamera(
        [Frame(index=i, payload=None, captured_at=float(i)) for i in range(1, 4)]
    )
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    asyncio.run(_run_until(viewer, 3))
    assert viewer.stats.displayed == 3
    assert isinstance(viewer.stats, ViewerStats)


async def _run_until(viewer: DiagnosticViewer, frames: int) -> None:
    """Run the viewer loop until `frames` were displayed or it stops."""
    await viewer.start()
    for _ in range(frames):
        if viewer.stats.displayed >= frames or viewer.user_closed:
            break
        await asyncio.sleep(0.005)
    await viewer.stop()


class FlakyRenderer(RecordingRenderer):
    def __init__(self, fail_on: int) -> None:
        super().__init__()
        self.fail_on = fail_on

    def render(self, frame, snapshot, context):
        if frame.index == self.fail_on:
            raise RuntimeError("render boom")
        return super().render(frame, snapshot, context)


def _array_frame(index: int) -> Frame:
    return Frame(index=index, payload=np.zeros((8, 8, 3), dtype=np.uint8), captured_at=float(index))


def test_viewer_survives_renderer_exception_and_degrades_to_raw():
    renderer = FlakyRenderer(fail_on=2)
    backend = FakeBackend()
    camera = FakeCamera([_array_frame(i) for i in range(1, 5)])
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    asyncio.run(_run_until(viewer, 4))
    assert viewer.stats.displayed == 3  # frame 2 failed, 1/3/4 rendered
    assert viewer.stats.render_errors == 1
    assert len(backend.frames) == 4  # degraded frame 2 still shown as raw copy
    assert backend.frames[1] is not None  # a frame reached the backend for frame 2


def test_viewer_keeps_rendering_after_renderer_failure():
    renderer = FlakyRenderer(fail_on=2)
    backend = FakeBackend()
    camera = FakeCamera([_array_frame(i) for i in range(1, 4)])
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    viewer.push(_snap(3))
    asyncio.run(_run_until(viewer, 3))
    assert viewer.stats.render_errors == 1
    assert renderer.seen[-1] == (3, 3)  # loop kept going after the failure


def test_viewer_syncs_anomaly_stats_from_renderer():
    renderer = DiagnosticRenderer()
    backend = FakeBackend()
    camera = FakeCamera([_array_frame(1)])
    viewer = DiagnosticViewer(camera, renderer, backend, display_interval_s=0.001)
    raw = RawHand(
        index=0,
        handedness="Right",
        category="Open_Palm",
        confidence=0.9,
        landmarks=(Landmark(1.5, 0.2, 0.0), Landmark(0.2, 0.3, 0.0), Landmark(0.3, 0.3, 0.0)),
    )
    now = time.monotonic()
    viewer.push(
        DiagnosticSnapshot(
            frame_index=1, created_at=now, captured_at=now, raw_hands=(raw,)
        )
    )
    asyncio.run(_run_until(viewer, 1))
    assert viewer.stats.out_of_bounds_landmarks == 1
    assert viewer.stats.nonfinite_landmarks == 0


class _MirrorRecordingRenderer(RecordingRenderer):
    mirror_seen: bool = False

    def render(self, frame, snapshot, context):
        self.mirror_seen = context.mirror
        return super().render(frame, snapshot, context)