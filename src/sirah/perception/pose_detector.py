"""MediaPipe Pose — body pose estimation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sirah.types import PoseEstimate

__all__ = ["PoseDetector"]

logger = logging.getLogger(__name__)


class PoseDetector:
    def __init__(
        self,
        static_image_mode: bool = False,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._static_image_mode = static_image_mode
        self._model_complexity = model_complexity
        self._min_detection_confidence = min_detection_confidence
        self._min_tracking_confidence = min_tracking_confidence
        self._pose: Any = None
        self._initialised = False

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._pose = await loop.run_in_executor(None, self._init_mp)
        self._initialised = True
        logger.info("PoseDetector: MediaPipe Pose started")

    async def stop(self) -> None:
        if self._pose is not None:
            self._pose.close()
            self._pose = None
        self._initialised = False

    async def health(self) -> bool:
        return self._initialised

    def _init_mp(self) -> object:
        import mediapipe as mp

        return mp.solutions.pose.Pose(
            static_image_mode=self._static_image_mode,
            model_complexity=self._model_complexity,
            min_detection_confidence=self._min_detection_confidence,
            min_tracking_confidence=self._min_tracking_confidence,
        )

    async def detect(self, frame_bgr: object) -> PoseEstimate | None:
        if not self._initialised or self._pose is None:
            return None

        loop = asyncio.get_running_loop()
        frame: Any = frame_bgr
        rgb: Any = frame[..., ::-1]

        def _run() -> PoseEstimate | None:
            results = self._pose.process(rgb)  # type: ignore[union-attr]
            if not results.pose_landmarks:
                return None
            landmarks = tuple(
                (lm.x, lm.y, lm.z) for lm in results.pose_landmarks.landmark
            )
            confidence = float(results.pose_landmarks.landmark[0].visibility or 0)
            return PoseEstimate(landmarks=landmarks, confidence=confidence)

        return await loop.run_in_executor(None, _run)
