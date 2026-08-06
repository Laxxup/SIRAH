"""OpenCV webcam capture — async frame generator."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from time import monotonic
from typing import TYPE_CHECKING, Any

from sirah.types import PerceptionFrame

if TYPE_CHECKING:
    import numpy as np
from sirah.perception.face_detector import FaceDetector
from sirah.perception.pose_detector import PoseDetector

__all__ = ["WebcamCapture"]

logger = logging.getLogger(__name__)


class WebcamCapture:
    def __init__(
        self,
        device: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        face_detector: FaceDetector | None = None,
        pose_detector: PoseDetector | None = None,
    ) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._face_detector = face_detector
        self._pose_detector = pose_detector
        self._cap: Any = None
        self._running = False
        self._frame_interval = 1.0 / max(fps, 1)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._cap = await loop.run_in_executor(None, self._open_camera)
        self._running = True
        logger.info("WebcamCapture: device %d started %dx%d", self._device, self._width, self._height)

    async def stop(self) -> None:
        self._running = False
        if self._cap is not None:
            self._cap.release()  # type: ignore[union-attr]
            self._cap = None

    async def health(self) -> bool:
        return self._running and self._cap is not None

    def _open_camera(self) -> object:
        import cv2

        cap = cv2.VideoCapture(self._device)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_FPS, self._fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera device {self._device}")
        return cap

    async def capture(self) -> PerceptionFrame:
        loop = asyncio.get_running_loop()
        t0 = monotonic()

        def _read() -> np.ndarray | None:
            import cv2

            ret, frame = self._cap.read()  # type: ignore[union-attr]
            if not ret or frame is None:
                return None
            return cv2.flip(frame, 1)

        frame = await loop.run_in_executor(None, _read)
        if frame is None:
            return PerceptionFrame(timestamp=t0)

        faces = ()
        if self._face_detector is not None:
            faces = await self._face_detector.detect(frame)

        pose = None
        if self._pose_detector is not None:
            pose = await self._pose_detector.detect(frame)

        return PerceptionFrame(
            timestamp=t0,
            faces=faces,
            pose=pose,
            frame_width=self._width,
            frame_height=self._height,
        )

    async def frames(self) -> AsyncIterator[PerceptionFrame]:
        while self._running:
            t_start = monotonic()
            frame = await self.capture()
            yield frame
            elapsed = monotonic() - t_start
            wait = self._frame_interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
