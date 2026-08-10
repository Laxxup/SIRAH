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
    """OpenCV YuNet adapter; model loading is explicit and local-only."""

    def __init__(
        self,
        model_path: Path,
        *,
        detector_factory: Callable[[Path], object] | None = None,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"YuNet model not found: {model_path}")
        self._detector = (detector_factory or _opencv_detector)(model_path)

    def detect(self, frame: Frame) -> GazeTarget | None:
        if frame.payload is None:
            return None
        height, width = frame.payload.shape[:2]  # type: ignore[attr-defined]
        self._detector.setInputSize((width, height))  # type: ignore[attr-defined]
        _, rows = self._detector.detect(frame.payload)  # type: ignore[attr-defined]
        if rows is None:
            return None
        faces = [
            FaceBox(float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[-1]))
            for row in rows
        ]
        face = select_largest_face(faces)
        return map_face(face, width=width, height=height) if face is not None else None


def _opencv_detector(model_path: Path) -> object:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('install perception support: pip install -e ".[perception]"') from exc
    return cv2.FaceDetectorYN.create(str(model_path), "", (320, 320))
