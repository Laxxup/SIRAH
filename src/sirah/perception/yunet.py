"""Pure YuNet detection helpers; OpenCV integration remains optional."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from sirah.perception.contracts import GazeTarget


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
