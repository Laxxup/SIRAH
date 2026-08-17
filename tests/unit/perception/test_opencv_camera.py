"""OpenCVCameraSource tests: deterministic (fake capture), no OpenCV or
hardware. `next_frame()` WAITS asynchronously for a new frame; `None` is
EOF only — the regression tests pin the startup race and the wait
semantics instead of polling around them.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

import pytest

from sirah.cli.perceive import perceive
from sirah.perception import opencv_camera
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.opencv_camera import OpenCVCameraSource


class FakeCapture:
    def __init__(self) -> None:
        self.released = False
        self.reads = 0

    def isOpened(self) -> bool:
        return True

    def read(self) -> tuple[bool, object]:
        self.reads += 1
        return True, {"frame": self.reads}

    def release(self) -> None:
        self.released = True


class FakeCaptureWithSet(FakeCapture):
    def __init__(self) -> None:
        super().__init__()
        self.settings: dict[object, object] = {}

    def set(self, prop: object, value: object) -> bool:
        self.settings[prop] = value
        return True


class GatedCapture(FakeCapture):
    """Capture that only produces a frame when the test opens its gate.

    Keeps the producer thread deterministic relative to the consumer so
    freshness counters can be asserted without real-time races.
    """

    def __init__(self, clock: Callable[[], float], gate: threading.Event) -> None:
        super().__init__()
        self._clock = clock
        self._gate = gate

    def read(self) -> tuple[bool, object]:
        while not self._gate.wait(timeout=0.05):
            pass
        self._gate.clear()
        self.reads += 1
        return True, {"frame": self.reads, "at": self._clock()}


class DelayedCapture(FakeCapture):
    """First read is delayed like a camera warm-up; then frames flow."""

    def __init__(self, delay_s: float) -> None:
        super().__init__()
        self._delay_s = delay_s
        self._first_done = False

    def read(self) -> tuple[bool, object]:
        if not self._first_done:
            time.sleep(self._delay_s)
            self._first_done = True
        self.reads += 1
        return True, {"frame": self.reads}


class _NoFaceDetector:
    def detect(self, frame: Frame) -> GazeTarget | None:
        return None


def _clock_control() -> tuple[Callable[[], float], dict[str, float]]:
    state = {"now": 100.0}

    def clock() -> float:
        return state["now"]

    return clock, state


async def _await_captured(source: OpenCVCameraSource, n: int) -> None:
    """Wait until the producer thread has stored `n` frames."""
    for _ in range(1000):
        if source.stats().captured >= n:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"captured never reached {n}")


async def _produce(
    source: OpenCVCameraSource,
    state: dict[str, float],
    gate: threading.Event,
    nows: tuple[float, ...],
) -> None:
    """Produce one frame per timestamp, waiting for each to be stored.

    `gate.set()` is a latch, not a counter: the next set must wait until
    the capture thread consumed the previous one.
    """
    for i, now in enumerate(nows, 1):
        state["now"] = now
        gate.set()
        await _await_captured(source, i)


async def test_next_frame_waits_for_slow_first_frame():
    """STARTUP RACE: a delayed first frame must NOT read as EOF."""
    source = OpenCVCameraSource(0, capture_factory=lambda _: DelayedCapture(0.2))
    await source.start()
    frame = await asyncio.wait_for(source.next_frame(), timeout=2.0)
    assert frame is not None  # old code returned None → perceived EOF
    assert frame.payload is not None
    await source.stop()


async def test_perceive_waits_for_slow_first_frame():
    """The reported bug end-to-end: sirah-perceive sees frames > 0."""
    source = OpenCVCameraSource(0, capture_factory=lambda _: DelayedCapture(0.15))
    summary = await perceive(source, _NoFaceDetector(), max_frames=3, interval_s=0.01)
    assert summary.frames == 3
    assert summary.faces == 0


async def test_camera_returns_latest_frame_and_releases_capture():
    capture = FakeCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None
    assert frame.payload is not None
    await source.stop()
    assert capture.released


async def test_stop_returns_eof_after_capture():
    capture = FakeCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None
    await source.stop()
    assert await source.next_frame() is None  # EOF after deliberate stop
    assert capture.released


async def test_frames_carry_monotonic_capture_timestamp():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    state["now"] = 250.0
    gate.set()  # produce one frame stamped at 250.0
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None and frame.captured_at == 250.0
    await source.stop()


async def test_stop_while_waiting_for_first_frame_is_eof_not_deadlock():
    """STOP WHILE WAITING: a waiter wakes and gets EOF, no leak."""
    clock, _ = _clock_control()
    gate = threading.Event()  # never set: the camera never produces
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    waiter = asyncio.create_task(source.next_frame())
    await asyncio.sleep(0.05)  # let the waiter block on the wait
    await asyncio.wait_for(source.stop(), timeout=2.0)
    assert await asyncio.wait_for(waiter, timeout=1.0) is None


async def test_cancelled_wait_leaves_camera_stoppable():
    """CANCELLATION: the await is interrupted, then stop() still works."""
    clock, _ = _clock_control()
    gate = threading.Event()  # never set
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    waiter = asyncio.create_task(source.next_frame())
    await asyncio.sleep(0.05)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.wait_for(source.stop(), timeout=2.0)
    assert await source.next_frame() is None  # still usable: EOF after stop


async def test_latest_frame_wins_when_producer_faster():
    """LATEST-FRAME: several frames before a read collapse into the newest."""
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    await _produce(source, state, gate, (300.0, 300.1, 300.2))
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None and frame.captured_at == 300.2  # newest only
    stats = source.stats()
    assert stats.captured == 3
    assert stats.consumed == 1
    assert stats.dropped == 2  # two frames were replaced before any read
    await source.stop()


async def test_stats_report_consumption_age():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    state["now"] = 300.0
    gate.set()  # frame stamped 300.0
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None and frame.captured_at == 300.0
    stats = source.stats()
    assert stats.consumed == 1
    assert stats.captured == 1
    assert stats.dropped == 0
    await source.stop()


async def test_stats_report_age_when_consumer_lags():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    state["now"] = 300.0
    gate.set()  # frame captured at 300.0
    await _await_captured(source, 1)
    state["now"] = 300.5  # the consumer only reads it half a second later
    frame = await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert frame is not None and frame.captured_at == 300.0
    assert source.stats().frame_age_s == pytest.approx(0.5)
    await source.stop()


async def test_stats_report_capture_fps():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()
    await _produce(source, state, gate, (100.0, 100.1, 100.2))
    await asyncio.wait_for(source.next_frame(), timeout=1.0)
    assert source.stats().capture_fps == pytest.approx(10.0)  # 2 / 0.2s
    await source.stop()


async def test_capture_settings_applied_when_capture_supports_set():
    capture = FakeCaptureWithSet()
    source = OpenCVCameraSource(
        0,
        width=1280,
        height=720,
        fps_target=30,
        capture_factory=lambda _: capture,
    )
    await source.start()
    await asyncio.sleep(0.005)
    assert capture.settings  # width/height (and fps) were applied
    await source.stop()


async def test_capture_settings_skipped_without_set_support():
    capture = FakeCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    await asyncio.sleep(0.005)
    assert capture.reads > 0  # still capturing
    await source.stop()


async def test_read_failure_raises_after_limit():
    class DyingCapture:
        def __init__(self) -> None:
            self.reads = 0
            self.released = False

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, object]:
            self.reads += 1
            return False, None

        def release(self) -> None:
            self.released = True

    source = OpenCVCameraSource(
        0, capture_factory=lambda _: DyingCapture(), read_failure_limit=3
    )
    await source.start()
    with pytest.raises(OSError, match="read failed"):
        await asyncio.wait_for(source.next_frame(), timeout=2.0)
    await source.stop()


async def test_transient_read_failures_reset_and_do_not_end_stream():
    class FlakyCapture:
        def __init__(self) -> None:
            self.reads = 0

        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, object]:
            self.reads += 1
            if self.reads <= 3:  # warm-up failures
                return False, None
            return True, {"frame": self.reads}

        def release(self) -> None:
            pass

    source = OpenCVCameraSource(
        0, capture_factory=lambda _: FlakyCapture(), read_failure_limit=5
    )
    await source.start()
    frame = await asyncio.wait_for(source.next_frame(), timeout=2.0)
    assert frame is not None  # transient failures did not end the stream
    await source.stop()


class RecordingCapture(FakeCapture):
    """Tracks which thread reads/releases and how many times."""

    def __init__(self) -> None:
        super().__init__()
        self.read_thread: int | None = None
        self.release_thread: int | None = None
        self.release_count = 0
        self._reading = threading.Event()

    def read(self) -> tuple[bool, object]:
        self.read_thread = threading.get_ident()
        self._reading.set()
        self.reads += 1
        return True, {"frame": self.reads}

    def release(self) -> None:
        self.release_count += 1
        self.release_thread = threading.get_ident()
        super().release()


class HeldReadCapture(FakeCapture):
    """Blocks inside `read()` until the test releases it (no frame)."""

    def __init__(self) -> None:
        super().__init__()
        self._entered_read = threading.Event()
        self._allow_read = threading.Event()
        self.release_count = 0

    def read(self) -> tuple[bool, object]:
        self._entered_read.set()
        self._allow_read.wait(timeout=5.0)
        self.reads += 1
        return True, {"frame": self.reads}

    def release(self) -> None:
        self.release_count += 1
        self.released = True


def _fake_cv2(monkeypatch, capture) -> dict:
    """Stub cv2 module recording how VideoCapture is called."""
    calls: list[tuple[object, object | None]] = []

    class _FakeCv2:
        CAP_V4L2 = 200

        def VideoCapture(self, device, backend=None):
            calls.append((device, backend))
            return capture

    monkeypatch.setattr(opencv_camera, "_opencv_module", lambda: _FakeCv2())
    return {"calls": calls}


def test_device_path_prefers_native_v4l2_backend(monkeypatch):
    """REGRESSION: /dev/videoN must open with CAP_V4L2, not CAP_ANY.

    The default backend maps the path to FFmpeg's libavdevice, whose
    teardown emits `ioctl(VIDIOC_QBUF): Bad file descriptor` on this
    camera. The native backend is requested explicitly.
    """
    calls = _fake_cv2(monkeypatch, FakeCapture())["calls"]
    opencv_camera._opencv_capture("/dev/video0")
    assert calls == [("/dev/video0", 200)]


def test_int_device_keeps_default_backend(monkeypatch):
    calls = _fake_cv2(monkeypatch, FakeCapture())["calls"]
    opencv_camera._opencv_capture(0)
    assert calls == [(0, None)]


def test_device_path_falls_back_when_v4l2_unavailable(monkeypatch):
    class NeverOpens:
        def __init__(self) -> None:
            self.released = False

        def isOpened(self) -> bool:
            return False

        def release(self) -> None:
            self.released = True

    never = NeverOpens()
    backup = FakeCapture()

    class _FakeCv2:
        CAP_V4L2 = 200

        def __init__(self) -> None:
            self._calls: list[tuple[object, object | None]] = []

        def VideoCapture(self, device, backend=None):
            self._calls.append((device, backend))
            return never if backend == 200 else backup

    fake = _FakeCv2()
    monkeypatch.setattr(opencv_camera, "_opencv_module", lambda: fake)
    result = opencv_camera._opencv_capture("/dev/video0")
    assert fake._calls == [("/dev/video0", 200), ("/dev/video0", None)]
    assert result is backup
    assert never.released  # the failed V4L2 handle was released, not leaked


async def test_stop_releases_capture_once_on_the_capture_thread():
    """OWNERSHIP: the capture thread releases, exactly once, never a reader."""
    capture = RecordingCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    await asyncio.sleep(0.01)  # let the producer thread take ownership
    assert capture._reading.wait(timeout=1.0)
    await source.stop()
    assert capture.released
    assert capture.release_count == 1  # released exactly once
    assert capture.release_thread == capture.read_thread  # same thread owns it
    assert capture.release_thread != threading.get_ident()  # not the caller


async def test_stop_never_releases_while_a_read_is_blocked():
    """RACE: a blocked driver read() must never be raced by release()."""
    capture = HeldReadCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    assert capture._entered_read.wait(timeout=1.0)  # worker is inside read()
    await source.stop()  # join times out; release must NOT happen here
    assert not capture.released  # release deferred to the worker's teardown
    assert capture.release_count == 0
    capture._allow_read.set()  # let the blocked read return
    for _ in range(200):
        if capture.released:
            break
        await asyncio.sleep(0.005)
    assert capture.released  # released by the worker once the read returned
    assert capture.release_count == 1


async def test_repeated_stop_releases_exactly_once():
    capture = RecordingCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)
    await source.start()
    await asyncio.sleep(0.01)
    await source.stop()
    await source.stop()  # idempotent
    assert capture.released
    assert capture.release_count == 1