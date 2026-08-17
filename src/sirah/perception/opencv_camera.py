"""Optional OpenCV USB camera source with non-blocking asyncio reads.

Captures on a worker thread and exposes ONLY the newest frame (latest-frame
semantics, ADR freshness rule): a slow consumer never accumulates a stale
queue. The source instruments capture rate, dropped frames and frame age so
operators can measure producer vs consumer balance on the Raspberry Pi.
"""

from __future__ import annotations

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
    """Capture on a worker thread and expose only the newest frame."""

    def __init__(
        self,
        device: int | str,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps_target: int | None = None,
        capture_factory: _CaptureFactory | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps_target = fps_target
        self._capture_factory = capture_factory
        self._clock = clock or time.monotonic
        self._capture: object | None = None
        self._latest: object | None = None
        self._latest_at: float | None = None
        self._index = 0
        self._captured = 0
        self._consumed = 0
        self._last_consumed_at: float | None = None
        self._frame_age: float | None = None
        self._capture_times: deque[float] = deque()
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
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    async def next_frame(self) -> Frame | None:
        with self._lock:
            if self._latest is None or self._latest_at is None:
                return None
            self._index += 1
            if self._latest_at != self._last_consumed_at:
                self._consumed += 1  # unique frames read; re-reads of the same frame do not inflate it
                self._last_consumed_at = self._latest_at
            self._frame_age = self._clock() - self._latest_at
            return Frame(index=self._index, payload=self._latest, captured_at=self._latest_at)

    async def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._capture is not None:
            self._capture.release()  # type: ignore[attr-defined]
        self._thread = None
        self._capture = None

    def stats(self) -> CameraStats:
        """Current freshness counters (thread-safe snapshot)."""
        with self._lock:
            pending = 1 if self._latest_at != self._last_consumed_at else 0
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
        assert self._capture is not None
        while not self._stop.is_set():
            ok, frame = self._capture.read()  # type: ignore[attr-defined]
            if ok:
                now = self._clock()
                with self._lock:
                    self._latest = frame
                    self._latest_at = now
                    self._captured += 1
                    self._capture_times.append(now)
            else:
                time.sleep(0.01)

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
    return _opencv_module().VideoCapture(device)  # type: ignore[attr-defined]


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