"""Optional MediaPipe Tasks vision with a Haar fallback."""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sirah.perception.face_detector import (
    FaceDetector,
    FaceVisualContext,
    VisualContext,
    _classify_color,
)
from sirah.types import FaceDetection

__all__ = [
    "HandInfo",
    "HandVisualContext",
    "MediaPipeVision",
    "count_extended_fingers",
    "smile_score_from_blendshapes",
]

logger = logging.getLogger(__name__)

SMILE_THRESHOLD = 0.35


@dataclass(frozen=True)
class HandInfo:
    handedness: str = "desconocida"
    fingers: tuple[bool, ...] = (False, False, False, False, False)
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @property
    def finger_count(self) -> int:
        return sum(self.fingers)


@dataclass(frozen=True)
class HandVisualContext:
    hands: tuple[HandInfo, ...] = ()

    @property
    def hand_count(self) -> int:
        return len(self.hands)

    @property
    def total_fingers(self) -> int:
        return sum(hand.finger_count for hand in self.hands)


def _distance(first: Any, second: Any) -> float:
    return math.hypot(float(first.x) - float(second.x), float(first.y) - float(second.y))


def count_extended_fingers(landmarks: Sequence[Any]) -> tuple[bool, ...]:
    """Count extended fingers from MediaPipe's 21 hand landmarks."""
    if len(landmarks) < 21:
        return (False, False, False, False, False)

    wrist = landmarks[0]
    thumb = _distance(landmarks[4], wrist) > _distance(landmarks[3], wrist) * 1.15
    extended = [thumb]
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        tip_farther = _distance(landmarks[tip], wrist) > _distance(landmarks[pip], wrist) * 1.05
        extended.append(float(landmarks[tip].y) < float(landmarks[pip].y) and tip_farther)
    return tuple(extended)


def smile_score_from_blendshapes(categories: Sequence[Any]) -> float:
    """Return the mean left/right smile blendshape score."""
    scores: list[float] = []
    target_names = {
        "mouthSmileLeft",
        "mouthSmileRight",
        "MOUTH_SMILE_LEFT",
        "MOUTH_SMILE_RIGHT",
    }
    for category in categories:
        if getattr(category, "category_name", "") in target_names:
            scores.append(float(getattr(category, "score", 0.0)))
    return sum(scores) / len(scores) if scores else 0.0


def _model_dir(model_dir: str | Path | None) -> Path:
    if model_dir is not None:
        return Path(model_dir).expanduser()
    configured = os.environ.get("SIRAH_MODELS_DIR")
    if configured:
        return Path(configured).expanduser()
    for candidate in (Path.cwd() / "models", Path.home() / "models"):
        if candidate.exists():
            return candidate
    return Path.cwd() / "models"


class MediaPipeVision(FaceDetector):
    """Face and hand perception using MediaPipe Tasks when models are present."""

    def __init__(
        self,
        model_dir: str | Path | None = None,
        num_faces: int = 4,
        num_hands: int = 2,
    ) -> None:
        super().__init__()
        self.model_dir = _model_dir(model_dir)
        self._num_faces = num_faces
        self._num_hands = num_hands
        self._face_landmarker: Any = None
        self._hand_landmarker: Any = None
        self._mediapipe_started = False

    async def start(self) -> None:
        face_path = self.model_dir / "face_landmarker.task"
        hand_path = self.model_dir / "hand_landmarker.task"
        if not face_path.is_file():
            logger.warning("Face model missing at %s; using Haar fallback", face_path)
            await super().start()
            return

        try:
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions

            self._face_landmarker = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(face_path)),
                    num_faces=self._num_faces,
                    output_face_blendshapes=True,
                    running_mode=vision.RunningMode.IMAGE,
                )
            )
            if hand_path.is_file():
                self._hand_landmarker = vision.HandLandmarker.create_from_options(
                    vision.HandLandmarkerOptions(
                        base_options=BaseOptions(model_asset_path=str(hand_path)),
                        num_hands=self._num_hands,
                        running_mode=vision.RunningMode.IMAGE,
                    )
                )
            else:
                logger.warning("Hand model missing at %s; hand vision disabled", hand_path)
            self._mediapipe_started = True
            self._initialised = True
            logger.info("MediaPipe Face/Hand Landmarkers started from %s", self.model_dir)
        except Exception as exc:
            logger.warning("MediaPipe unavailable (%s); using Haar fallback", exc)
            self._face_landmarker = None
            self._hand_landmarker = None
            await super().start()

    async def stop(self) -> None:
        for landmarker in (self._face_landmarker, self._hand_landmarker):
            if landmarker is not None:
                landmarker.close()
        self._face_landmarker = None
        self._hand_landmarker = None
        self._mediapipe_started = False
        self._initialised = False
        if self._cascade is not None:
            await super().stop()

    async def health(self) -> bool:
        return self._initialised and (
            self._face_landmarker is not None or self._cascade is not None
        )

    @staticmethod
    def _to_image(frame: object) -> Any:
        import cv2
        import mediapipe as mp

        frame_any: Any = frame
        rgb = cv2.cvtColor(frame_any, cv2.COLOR_BGR2RGB)
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    @staticmethod
    def _bbox(landmarks: Sequence[Any], width: int, height: int) -> tuple[int, int, int, int]:
        x_values = [min(1.0, max(0.0, float(point.x))) for point in landmarks]
        y_values = [min(1.0, max(0.0, float(point.y))) for point in landmarks]
        x1 = int(min(x_values) * width)
        y1 = int(min(y_values) * height)
        x2 = max(x1 + 1, int(max(x_values) * width))
        y2 = max(y1 + 1, int(max(y_values) * height))
        return x1, y1, min(width, x2), min(height, y2)

    @staticmethod
    def _lighting(gray: Any) -> str:
        import numpy as np

        brightness = float(np.mean(gray)) / 255.0
        if brightness < 0.3:
            return "oscura"
        if brightness > 0.7:
            return "muy iluminada"
        return "normal"

    @staticmethod
    def _torso_bbox(
        frame: Any,
        bbox: tuple[int, int, int, int],
        x_limits: tuple[int, int] | None = None,
    ) -> tuple[int, int, int, int]:
        height, width = frame.shape[:2]
        x1_face, y1_face, x2_face, y2_face = bbox
        face_width = max(1, x2_face - x1_face)
        face_height = max(1, y2_face - y1_face)
        x1 = max(0, int(x1_face - face_width * 0.6))
        x2 = min(width, int(x2_face + face_width * 0.8))
        if x_limits is not None:
            x1 = max(x1, x_limits[0])
            x2 = min(x2, x_limits[1])
        y1 = max(0, min(height, y2_face))
        y2 = min(height, int(y2_face + face_height * 1.8))
        if y2 - y1 < max(8, int(face_height * 0.35)):
            y1 = max(0, height - max(8, face_height))
            y2 = height
        return x1, y1, max(x1, x2), max(y1, y2)

    @classmethod
    def _color(
        cls,
        frame: Any,
        bbox: tuple[int, int, int, int],
        x_limits: tuple[int, int] | None = None,
    ) -> str:
        import numpy as np

        torso_x1, torso_y1, torso_x2, torso_y2 = cls._torso_bbox(
            frame, bbox, x_limits
        )
        if torso_y2 <= torso_y1 or torso_x2 <= torso_x1:
            return "desconocido"
        pixels = frame[torso_y1:torso_y2, torso_x1:torso_x2]
        if pixels.size == 0:
            return "desconocido"
        pixels = pixels.reshape(-1, 3).astype(float)
        visible = pixels.max(axis=1) > 30
        clipped = pixels.min(axis=1) > 235
        samples = pixels[visible & ~clipped]
        return _classify_color(np.median(samples if samples.size else pixels, axis=0))

    def _face_context(
        self,
        frame: Any,
        landmarks: Sequence[Any],
        smile_score: float,
        lighting: str,
        x_limits: tuple[int, int] | None = None,
    ) -> tuple[tuple[int, int, int, int], FaceVisualContext]:
        height, width = frame.shape[:2]
        bbox = self._bbox(landmarks, width, height)
        x1, y1, x2, y2 = bbox
        face_width = max(1, x2 - x1)
        face_height = max(1, y2 - y1)
        center_x = (x1 + x2) / 2.0 / width
        if center_x < 0.35:
            position = "izquierda"
        elif center_x > 0.65:
            position = "derecha"
        else:
            position = "centro"
        face_area = face_width * face_height / (width * height)
        distance = "cerca" if face_area > 0.15 else "media" if face_area > 0.05 else "lejos"
        torso = self._torso_bbox(frame, bbox, x_limits)
        return bbox, FaceVisualContext(
            dominant_color=self._color(frame, bbox, x_limits),
            smiling=smile_score >= SMILE_THRESHOLD,
            smile_score=smile_score,
            face_position=position,
            face_distance=distance,
            lighting=lighting,
            smile_source="blendshape",
            torso_bbox=(
                torso[0] / width,
                torso[1] / height,
                (torso[2] - torso[0]) / width,
                (torso[3] - torso[1]) / height,
            ),
        )

    def _face_data(self, frame: Any) -> tuple[tuple[FaceDetection, ...], VisualContext]:
        import cv2

        result = self._face_landmarker.detect(self._to_image(frame))
        height, width = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lighting = self._lighting(gray)
        raw_entries: list[tuple[tuple[int, int, int, int], Sequence[Any], float]] = []
        blendshapes = getattr(result, "face_blendshapes", ())
        for index, landmarks in enumerate(getattr(result, "face_landmarks", ())):
            categories = blendshapes[index] if index < len(blendshapes) else ()
            score = smile_score_from_blendshapes(categories)
            raw_entries.append((self._bbox(landmarks, width, height), landmarks, score))
        raw_entries.sort(key=lambda entry: entry[0][0])
        entries: list[tuple[tuple[int, int, int, int], FaceVisualContext]] = []
        for index, (bbox, landmarks, score) in enumerate(raw_entries):
            left_limit = (
                (raw_entries[index - 1][0][0] + raw_entries[index - 1][0][2]) // 2
                if index
                else 0
            )
            right_limit = (
                (bbox[2] + raw_entries[index + 1][0][0]) // 2
                if index + 1 < len(raw_entries)
                else width
                if index + 1 < len(raw_entries)
                else width
            )
            entries.append(
                self._face_context(
                    frame,
                    landmarks,
                    score,
                    lighting,
                    (left_limit, right_limit),
                )
            )
        contexts = tuple(entry[1] for entry in entries)
        detections = tuple(
            FaceDetection(
                bbox=(
                    x1 / width,
                    y1 / height,
                    (x2 - x1) / width,
                    (y2 - y1) / height,
                ),
                confidence=0.9,
            )
            for x1, y1, x2, y2 in (entry[0] for entry in entries)
        )
        colors = [
            context.dominant_color
            for context in contexts
            if context.dominant_color != "desconocido"
        ]
        dominant = colors[0] if len(set(colors)) <= 1 and colors else "varios"
        context = VisualContext(
            face_count=len(contexts),
            dominant_color=dominant,
            smiling=all(context.smiling for context in contexts),
            face_position=contexts[0].face_position if contexts else "centro",
            face_distance=contexts[0].face_distance if contexts else "media",
            lighting=lighting,
            face_contexts=contexts,
        )
        return detections, context

    async def detect(self, frame_bgr: object) -> tuple[FaceDetection, ...]:
        if not self._mediapipe_started:
            return await super().detect(frame_bgr)
        import asyncio

        loop = asyncio.get_running_loop()
        detections, _ = await loop.run_in_executor(None, self._face_data, frame_bgr)
        return detections

    async def analyze(self, frame_bgr: object) -> VisualContext:
        if not self._mediapipe_started:
            return await super().analyze(frame_bgr)
        import asyncio

        loop = asyncio.get_running_loop()
        _, context = await loop.run_in_executor(None, self._face_data, frame_bgr)
        return context

    def _hand_data(self, frame: Any) -> HandVisualContext:
        result = self._hand_landmarker.detect(self._to_image(frame))
        hands: list[HandInfo] = []
        for index, landmarks in enumerate(getattr(result, "hand_landmarks", ())):
            handedness_values = getattr(result, "handedness", ())
            categories = handedness_values[index] if index < len(handedness_values) else ()
            handedness = (
                getattr(categories[0], "category_name", "desconocida")
                if categories
                else "desconocida"
            )
            height, width = frame.shape[:2]
            x, y, x2, y2 = self._bbox(landmarks, width, height)
            hands.append(
                HandInfo(
                    handedness=handedness,
                    fingers=count_extended_fingers(landmarks),
                    bbox=(
                        x / width,
                        y / height,
                        (x2 - x) / width,
                        (y2 - y) / height,
                    ),
                )
            )
        return HandVisualContext(hands=tuple(hands))

    async def analyze_hands(self, frame_bgr: object) -> HandVisualContext:
        if not self._mediapipe_started or self._hand_landmarker is None:
            return HandVisualContext()
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._hand_data, frame_bgr)
