"""Optional OpenCV USB camera source with non-blocking asyncio reads.

Captures on a worker thread and exposes ONLY the newest frame (latest-frame
semantics, ADR freshness rule): a slow consumer never accumulates a stale
queue. The source instruments capture rate, dropped frames and frame age so
operators can measure producer vs consumer balance on the Raspberry Pi.

`next_frame()` WAITS asynchronously (yielding the event loop) for the next
new frame instead of returning None when nothing is ready yet. The capture
thread signals the loop through `loop.call_soon_threadsafe` — the canonical
thread→asyncio bridge — so the wait is event-driven, not a polling spin.
`None` is returned only after `stop()`; a terminal read failure raises
`OSError` so the owner degrades explicitly (registry rule).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from sirah.perception.contracts import Frame

_CaptureFactory = Callable[[int | str], object]

DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
_FPS_WINDOW_S = 1.0
_READ_RETRY_SLEEP_S = 0.05


@dataclass(frozen=True)
class CameraStats:
    """Freshness counters for one camera source session.

    `captured` is frames produced by the capture thread; `consumed` is
    frames handed to consumers; `dropped` is frames replaced before any
    consumer read them (producer outruns consumer). `capture_fps` is the
    recent production rate and `frame_age_s` the age of the last consumed
    frame — a growing `dropped`/`frame_age_s` signals a too-slow consumer.
    """

    captured: int
    consumed: int
    dropped: int
    capture_fps: float
    frame_age_s: float | None


class OpenCVCameraSource:
    """Capture on a worker thread and expose only the newest frame.

    Waits for frames asynchronously: `next_frame()` blocks the caller's
    coroutine (not the loop) until the capture thread stores a NEW frame
    or the stream ends. Multiple frames produced before a read collapse
    into the newest one — old productions are counted as dropped.
    """

    def __init__(
        self,
        device: int | str,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps_target: int | None = None,
        capture_factory: _CaptureFactory | None = None,
        clock: Callable[[], float] | None = None,
        read_failure_limit: int = 10,
    ) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps_target = fps_target
        self._capture_factory = capture_factory
        self._clock = clock or time.monotonic
        self._read_failure_limit = max(1, read_failure_limit)
        self._capture: object | None = None
        self._latest: object | None = None
        self._latest_at: float | None = None
        self._latest_seq = 0  # production sequence of the stored newest frame
        self._delivered_seq = 0  # sequence of the last frame handed to a consumer
        self._index = 0
        self._captured = 0
        self._consumed = 0
        self._frame_age: float | None = None
        self._capture_times: deque[float] = deque()
        self._read_failures = 0
        self._ended = False
        self._failure_reason: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wakeup: asyncio.Event | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        factory = self._capture_factory or _opencv_capture
        capture = factory(self._device)
        if not capture.isOpened():  # type: ignore[attr-defined]
            raise OSError(f"cannot open camera {self._device!r}")
        self._apply_capture_settings(capture)
        self._capture = capture
        self._loop = asyncio.get_running_loop()
        self._wakeup = asyncio.Event()
        self._stop.clear()
        with self._lock:
            self._latest = None
            self._latest_at = None
            self._latest_seq = 0
            self._delivered_seq = 0
            self._index = 0
            self._captured = 0
            self._consumed = 0
            self._frame_age = None
            self._capture_times.clear()
            self._read_failures = 0
            self._ended = False
            self._failure_reason = None
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    async def next_frame(self) -> Frame | None:
        """Return the newest frame, waiting asynchronously for one.

        Blocks the calling coroutine — never the loop — until the capture
        thread stores a frame not yet delivered (returns it), the source
        is stopped (returns None = EOF), or a terminal read failure ended
        it (raises OSError). Cancellation interrupts the wait cleanly.
        """
        while True:
            wakeup = self._wakeup
            if wakeup is not None:
                wakeup.clear()
            with self._lock:
                if self._ended:
                    return self._eof_or_raise_locked()
                if self._latest is not None and self._latest_seq != self._delivered_seq:
                    assert self._latest_at is not None
                    self._delivered_seq = self._latest_seq
                    self._consumed += 1
                    self._index += 1
                    self._frame_age = self._clock() - self._latest_at
                    return Frame(
                        index=self._index,
                        payload=self._latest,
                        captured_at=self._latest_at,
                    )
            if wakeup is None:
                return None  # not started: no stream, treat as EOF
            await wakeup.wait()

    async def stop(self) -> None:
        """Signal the worker to stop; the worker owns the release.

        Deliberate stop is an EOF: waiters wake and `next_frame` returns
        None. The capture is released by the capture thread itself in its
        teardown, so `release()` can never race an in-flight driver
        `read()` from another thread. If the worker is blocked in a driver
        `read()` the join times out and the daemon thread releases the
        capture when the read returns (documented lifecycle risk, not a
        deadlock).
        """
        self._stop.set()
        with self._lock:
            self._ended = True
        if self._wakeup is not None:
            self._wakeup.set()  # wake any waiter from the loop side
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._capture = None

    def stats(self) -> CameraStats:
        """Current freshness counters (thread-safe snapshot)."""
        with self._lock:
            pending = 1 if self._latest_seq != self._delivered_seq else 0
            dropped = max(0, self._captured - self._consumed - pending)
            return CameraStats(
                captured=self._captured,
                consumed=self._consumed,
                dropped=dropped,
                capture_fps=self._capture_fps_locked(),
                frame_age_s=self._frame_age,
            )

    def _apply_capture_settings(self, capture: object) -> None:
        setter = getattr(capture, "set", None)
        if setter is None:
            return
        cv2 = _opencv_module_or_none()
        if cv2 is None:
            return  # optional extra absent; capture resolution stays vendor default
        setter(cv2.CAP_PROP_FRAME_WIDTH, self._width)  # type: ignore[attr-defined]
        setter(cv2.CAP_PROP_FRAME_HEIGHT, self._height)  # type: ignore[attr-defined]
        if self._fps_target is not None:
            setter(cv2.CAP_PROP_FPS, self._fps_target)  # type: ignore[attr-defined]

    def _capture_loop(self) -> None:
        capture = self._capture
        assert capture is not None
        try:
            while not self._stop.is_set():
                ok, frame = capture.read()  # type: ignore[attr-defined]
                if ok:
                    now = self._clock()
                    with self._lock:
                        self._latest = frame
                        self._latest_at = now
                        self._captured += 1
                        self._latest_seq = self._captured
                        self._read_failures = 0
                        self._capture_times.append(now)
                    self._notify()
                else:
                    with self._lock:
                        self._read_failures += 1
                        failed = self._read_failures >= self._read_failure_limit
                        if failed:
                            self._ended = True
                            self._failure_reason = (
                                f"camera {self._device!r} read failed "
                                f"{self._read_failures} times consecutively"
                            )
                    if failed:
                        self._notify()
                        break
                    time.sleep(_READ_RETRY_SLEEP_S)
        finally:
            capture.release()  # type: ignore[attr-defined]

    def _notify(self) -> None:
        """Wake the event loop from the capture thread (thread-safe)."""
        wakeup = self._wakeup
        loop = self._loop
        if wakeup is None or loop is None:
            return
        try:
            loop.call_soon_threadsafe(wakeup.set)
        except RuntimeError:
            pass  # loop closed during teardown; no one is waiting

    def _eof_or_raise_locked(self) -> Frame | None:
        """Resolve an ended stream: stop → None, terminal failure → raise."""
        if not self._stop.is_set() and self._failure_reason is not None:
            raise OSError(self._failure_reason)
        return None

    def _capture_fps_locked(self) -> float:
        now = self._clock()
        while self._capture_times and now - self._capture_times[0] > _FPS_WINDOW_S:
            self._capture_times.popleft()
        if len(self._capture_times) < 2:
            return 0.0
        window = self._capture_times[-1] - self._capture_times[0]
        if window <= 0:
            return 0.0
        return (len(self._capture_times) - 1) / window


def _opencv_capture(device: int | str) -> object:
    """Open `device`, preferring the native V4L2 backend for device paths.

    The default CAP_ANY backend maps `/dev/videoN` to FFmpeg's libavdevice
    V4L2 module, whose teardown emits ``ioctl(VIDIOC_QBUF): Bad file
    descriptor`` on some UVC cameras. The native CAP_V4L2 backend closes
    cleanly, so device paths open with it first and fall back to CAP_ANY
    only when it cannot open the device at all.
    """
    cv2 = _opencv_module()
    if isinstance(device, str) and device.startswith("/dev/video"):
        capture = cv2.VideoCapture(device, cv2.CAP_V4L2)  # type: ignore[attr-defined]
        if capture.isOpened():
            return capture
        capture.release()
    return cv2.VideoCapture(device)  # type: ignore[attr-defined]


def _opencv_module() -> object:
    cv2 = _opencv_module_or_none()
    if cv2 is None:
        raise RuntimeError('install perception support: pip install -e ".[perception]"')
    return cv2


def _opencv_module_or_none() -> object | None:
    try:
        import cv2
    except ImportError:
        return None
    return cv2