"""MediaPipe FaceDetection — lightweight face detection for Pi 4B."""

from __future__ import annotations

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from sirah.types import FaceDetection, PerceptionFrame

if TYPE_CHECKING:
    import numpy as np

__all__ = ["FaceDetector"]

logger = logging.getLogger(__name__)


class FaceDetector:
    def __init__(
        self,
        model_selection: int = 0,
        min_detection_confidence: float = 0.5,
    ) -> None:
        self._model_selection = model_selection
        self._min_detection_confidence = min_detection_confidence
        self._face_detection = None
        self._initialised = False

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._face_detection = await loop.run_in_executor(None, self._init_mp)
        self._initialised = True
        logger.info("FaceDetector: MediaPipe FaceDetection started")

    async def stop(self) -> None:
        if self._face_detection is not None:
            self._face_detection.close()
            self._face_detection = None
        self._initialised = False

    async def health(self) -> bool:
        return self._initialised and self._face_detection is not None

    def _init_mp(self) -> object:
        import mediapipe as mp

        return mp.solutions.face_detection.FaceDetection(
            model_selection=self._model_selection,
            min_detection_confidence=self._min_detection_confidence,
        )

    async def detect(self, frame_bgr: object) -> tuple[FaceDetection, ...]:
        if not self._initialised or self._face_detection is None:
            return ()

        loop = asyncio.get_running_loop()
        rgb = frame_bgr[..., ::-1]

        def _run() -> tuple[FaceDetection, ...]:
            results = self._face_detection.process(rgb)  # type: ignore[union-attr]
            if not results.detections:
                return ()
            h, w = frame_bgr.shape[:2]
            faces: list[FaceDetection] = []
            for det in results.detections:
                bbox = det.location_data.relative_bounding_box
                faces.append(
                    FaceDetection(
                        bbox=(bbox.xmin, bbox.ymin, bbox.width, bbox.height),
                        confidence=float(det.score[0]) if det.score else 0.0,
                        face_id=det.label_id[0] if det.label_id else -1,
                    )
                )
            return tuple(faces)

        return await loop.run_in_executor(None, _run)
