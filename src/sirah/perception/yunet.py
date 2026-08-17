"""Pure YuNet detection helpers; OpenCV integration remains optional."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sirah.perception.contracts import Frame, GazeTarget


@dataclass(frozen=True)
class FaceBox:
    x: float
    y: float
    width: float
    height: float
    confidence: float


def select_largest_face(faces: Sequence[FaceBox]) -> FaceBox | None:
    """Select the primary face deterministically by bounding-box area."""
    return max(faces, key=lambda face: face.width * face.height, default=None)


def map_face(face: FaceBox, *, width: int, height: int) -> GazeTarget:
    """Map an image-space face center to A1 normalized world coordinates."""
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    center_x = face.x + face.width / 2
    center_y = face.y + face.height / 2
    x = max(-1.0, min(1.0, 2 * center_x / width - 1))
    y = max(-1.0, min(1.0, 1 - 2 * center_y / height))
    return GazeTarget(x, y, confidence=face.confidence)


class YuNetFaceDetector:
    """OpenCV YuNet adapter; model loading is explicit and local-only.

    Implements both contracts: `detect` (largest face, backwards
    compatible) and `detect_many` (every face, for the attention layer).
    """

    def __init__(
        self,
        model_path: Path,
        *,
        detector_factory: Callable[[Path], object] | None = None,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"YuNet model not found: {model_path}")
        self._detector = (detector_factory or _opencv_detector)(model_path)
        self._width = 0
        self._height = 0

    def detect(self, frame: Frame) -> GazeTarget | None:
        face = select_largest_face(self._boxes(frame))
        return (
            map_face(face, width=self._width, height=self._height)
            if face is not None
            else None
        )

    def detect_many(self, frame: Frame) -> Sequence[GazeTarget]:
        return [
            map_face(face, width=self._width, height=self._height)
            for face in self._boxes(frame)
        ]

    def _boxes(self, frame: Frame) -> Sequence[FaceBox]:
        if frame.payload is None:
            return []
        self._height, self._width = frame.payload.shape[:2]  # type: ignore[attr-defined]
        self._detector.setInputSize((self._width, self._height))  # type: ignore[attr-defined]
        _, rows = self._detector.detect(frame.payload)  # type: ignore[attr-defined]
        if rows is None:
            return []
        return [
            FaceBox(float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[-1]))
            for row in rows
        ]


def _opencv_detector(model_path: Path) -> object:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('install perception support: pip install -e ".[perception]"') from exc
    return cv2.FaceDetectorYN.create(str(model_path), "", (320, 320))
