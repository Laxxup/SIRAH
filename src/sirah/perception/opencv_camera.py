"""Optional OpenCV USB camera source with non-blocking asyncio reads."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from sirah.perception.contracts import Frame

_CaptureFactory = Callable[[int | str], object]


class OpenCVCameraSource:
    """Capture on a worker thread and expose only the newest frame."""

    def __init__(
        self, device: int | str, *, capture_factory: _CaptureFactory | None = None
    ) -> None:
        self._device = device
        self._capture_factory = capture_factory
        self._capture: object | None = None
        self._latest: object | None = None
        self._index = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        factory = self._capture_factory or _opencv_capture
        capture = factory(self._device)
        if not capture.isOpened():  # type: ignore[attr-defined]
            raise OSError(f"cannot open camera {self._device!r}")
        self._capture = capture
        self._stop.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    async def next_frame(self) -> Frame | None:
        with self._lock:
            if self._latest is None:
                return None
            self._index += 1
            return Frame(index=self._index, payload=self._latest)

    async def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._capture is not None:
            self._capture.release()  # type: ignore[attr-defined]
        self._thread = None
        self._capture = None

    def _capture_loop(self) -> None:
        assert self._capture is not None
        while not self._stop.is_set():
            ok, frame = self._capture.read()  # type: ignore[attr-defined]
            if ok:
                with self._lock:
                    self._latest = frame
            else:
                time.sleep(0.01)


def _opencv_capture(device: int | str) -> object:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('install perception support: pip install -e ".[perception]"') from exc
    return cv2.VideoCapture(device)
