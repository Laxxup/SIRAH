from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

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


def _clock_control() -> tuple[Callable[[], float], dict[str, float]]:
    state = {"now": 100.0}

    def clock() -> float:
        return state["now"]

    return clock, state


async def _drain(source: OpenCVCameraSource, expected_at: float | None = None) -> object:
    for _ in range(500):
        frame = await source.next_frame()
        if frame is not None and (expected_at is None or frame.captured_at == expected_at):
            return frame
        await asyncio.sleep(0.001)
    raise AssertionError(f"no frame with captured_at={expected_at} arrived")


async def test_camera_returns_latest_frame_and_releases_capture():
    capture = FakeCapture()
    source = OpenCVCameraSource(0, capture_factory=lambda _: capture)

    await source.start()
    for _ in range(20):
        frame = await source.next_frame()
        if frame is not None:
            break
        await asyncio.sleep(0.001)

    assert frame is not None
    assert frame.payload is not None
    await source.stop()
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
    frame = await _drain(source)
    assert frame.captured_at == 250.0
    await source.stop()


async def test_stats_report_age_and_dropped_frames():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()

    state["now"] = 300.0
    gate.set()  # frame #1 stamped 300.0
    consumed = await _drain(source)
    assert consumed.captured_at == 300.0

    state["now"] = 300.25  # 250 ms later: the frame we read is now stale
    again = await source.next_frame()  # re-read of the SAME frame
    assert again.captured_at == 300.0
    stats = source.stats()
    assert stats.consumed == 1  # unique frames read, re-reads ignored
    assert stats.captured == 1
    assert stats.frame_age_s == 0.25

    state["now"] = 300.4
    gate.set()  # frame #2 stamped 300.4 (frame #1 was never replaced before its read)
    second = await _drain(source, expected_at=300.4)
    assert second.captured_at == 300.4
    await source.stop()
    stats = source.stats()
    assert stats.captured == 2
    assert stats.consumed == 2
    assert stats.dropped == 0  # both produced frames were consumed


async def test_dropped_frames_count_replaced_productions():
    clock, state = _clock_control()
    gate = threading.Event()
    source = OpenCVCameraSource(
        0, capture_factory=lambda _: GatedCapture(clock, gate), clock=clock
    )
    await source.start()

    # Produce three frames (300.0, 300.1, 300.2) BEFORE any consumer read.
    for now in (300.0, 300.1, 300.2):
        state["now"] = now
        gate.set()
        await asyncio.sleep(0.01)

    consumed = await _drain(source, expected_at=300.2)  # consumer reads only the newest
    assert consumed.captured_at == 300.2
    stats = source.stats()
    assert stats.captured == 3
    assert stats.consumed == 1
    assert stats.dropped == 2  # two frames were replaced before any read
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