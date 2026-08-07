"""Face detector using OpenCV Haar Cascade + visual context extraction."""

from __future__ import annotations

import asyncio
import colorsys
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from sirah.types import FaceDetection

__all__ = ["FaceDetector", "FaceVisualContext", "VisualContext"]

logger = logging.getLogger(__name__)


def _get_cascade_path() -> str:
    import cv2

    venv_cv2 = os.path.join(
        os.path.dirname(sys.executable), "..", "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages", "cv2", "data", "haarcascade_frontalface_default.xml",
    )
    candidates = [
        os.path.join(
            cv2.data.haarcascades,  # type: ignore[attr-defined]
            "haarcascade_frontalface_default.xml",
        ),
        os.path.abspath(venv_cv2),
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def _get_smile_cascade_path() -> str:
    cv2_data = os.path.dirname(_get_cascade_path())
    candidates = [
        os.path.join(cv2_data, "haarcascade_smile.xml"),
        "/usr/share/opencv4/haarcascades/haarcascade_smile.xml",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


@dataclass
class FaceVisualContext:
    dominant_color: str = "desconocido"
    smiling: bool = False
    smile_score: float = 0.0
    face_position: str = "centro"
    face_distance: str = "media"
    lighting: str = "normal"
    smile_source: str = "boolean"
    torso_bbox: tuple[float, float, float, float] | None = None


@dataclass
class VisualContext:
    face_count: int
    dominant_color: str = "desconocido"
    smiling: bool = False
    face_position: str = "centro"
    face_distance: str = "media"
    lighting: str = "normal"
    face_contexts: tuple[FaceVisualContext, ...] = ()
    hands: Any = ()


def _classify_color(bgr: object) -> str:
    """Classify a BGR sample, tolerant of indoor lighting and low saturation."""
    import numpy as np

    values = np.asarray(bgr, dtype=float).reshape(-1)
    if values.size < 3:
        return "desconocido"

    blue, green, red = (float(value) for value in values[:3])
    maximum = max(blue, green, red)
    minimum = min(blue, green, red)
    spread = maximum - minimum

    if maximum < 30:
        return "negro"
    if maximum > 235 and spread < 30:
        return "blanco"

    hue, saturation, value = colorsys.rgb_to_hsv(
        red / 255.0, green / 255.0, blue / 255.0
    )

    if saturation < 0.15:
        if maximum < 120:
            return "gris oscuro"
        if maximum > 200:
            return "blanco"
        return "gris"
    if value < 0.25:
        return "gris oscuro"

    if hue < 0.03 or hue >= 0.97:
        return "rojo"
    if hue < 0.08:
        return "naranja" if saturation > 0.4 else "cafe"
    if hue < 0.16:
        return "amarillo"
    if hue < 0.22:
        return "amarillo verdoso"
    if hue < 0.42:
        return "verde"
    if hue < 0.52:
        return "verde azulado"
    if hue < 0.62:
        return "azul claro"
    if hue < 0.72:
        return "azul"
    if hue < 0.82:
        return "azul oscuro"
    if hue < 0.90:
        return "morado"
    return "rosa"


class FaceDetector:
    def __init__(
        self,
        model_selection: int = 0,
        min_detection_confidence: float = 0.5,
    ) -> None:
        self._min_detection_confidence = min_detection_confidence
        self._cascade: Any = None
        self._smile_cascade: Any = None
        self._initialised = False

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._cascade = await loop.run_in_executor(None, self._init_cv)
        self._smile_cascade = await loop.run_in_executor(None, self._init_smile)
        self._initialised = True
        logger.info("FaceDetector: OpenCV Haar Cascades started")

    async def stop(self) -> None:
        self._cascade = None
        self._smile_cascade = None
        self._initialised = False

    async def health(self) -> bool:
        return self._initialised and self._cascade is not None

    def _init_cv(self) -> object:
        import cv2

        cascade = cv2.CascadeClassifier(_get_cascade_path())
        if cascade.empty():
            raise RuntimeError(f"Cannot load cascade: {_get_cascade_path()}")
        return cascade

    def _init_smile(self) -> object | None:
        import cv2

        path = _get_smile_cascade_path()
        if not os.path.exists(path):
            return None
        cascade = cv2.CascadeClassifier(path)
        return cascade if not cascade.empty() else None

    async def detect(self, frame_bgr: object) -> tuple[FaceDetection, ...]:
        if not self._initialised or self._cascade is None:
            return ()

        import cv2

        loop = asyncio.get_running_loop()

        def _run() -> tuple[FaceDetection, ...]:
            frame: Any = frame_bgr
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            gray = cv2.equalizeHist(gray)
            faces = self._cascade.detectMultiScale(  # type: ignore[union-attr]
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40),
            )
            ordered_faces = sorted(
                (
                    (int(face[0]), int(face[1]), int(face[2]), int(face[3]))
                    for face in faces
                ),
                key=lambda face: face[0],
            )
            return tuple(
                FaceDetection(
                    bbox=(x / w, y / h, fw / w, fh / h),
                    confidence=0.8,
                )
                for (x, y, fw, fh) in ordered_faces
            )

        return await loop.run_in_executor(None, _run)

    async def analyze(self, frame_bgr: object) -> VisualContext:
        import cv2
        import numpy as np

        loop = asyncio.get_running_loop()

        def _run() -> VisualContext:
            frame: Any = frame_bgr
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            gray = cv2.equalizeHist(gray)
            faces = self._cascade.detectMultiScale(  # type: ignore[union-attr]
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40),
            )

            if len(faces) == 0:
                return VisualContext(face_count=0)

            brightness = float(np.mean(gray)) / 255.0
            if brightness < 0.3:
                light = "oscura"
            elif brightness > 0.7:
                light = "muy iluminada"
            else:
                light = "normal"

            def _analyze_face(face: tuple[int, int, int, int]) -> FaceVisualContext:
                x, y, fw, fh = face
                center_x = (x + fw // 2) / w
                if center_x < 0.35:
                    pos = "izquierda"
                elif center_x > 0.65:
                    pos = "derecha"
                else:
                    pos = "centro"

                face_area = (fw * fh) / (w * h)
                if face_area > 0.15:
                    dist = "cerca"
                elif face_area > 0.05:
                    dist = "media"
                else:
                    dist = "lejos"

                smiling = False
                if self._smile_cascade is not None and face_area >= 0.01:
                    roi_gray = gray[y + (2 * fh) // 3 : y + fh, x : x + fw]
                    if roi_gray.size > 0:
                        roi_gray = cv2.equalizeHist(roi_gray)
                        min_size = (max(12, fw // 6), max(8, fh // 12))
                        smiles = self._smile_cascade.detectMultiScale(
                            roi_gray,
                            scaleFactor=1.3,
                            minNeighbors=12,
                            minSize=min_size,
                            maxSize=(max(min_size[0] + 1, fw // 2),
                                     max(min_size[1] + 1, fh // 3)),
                        )
                        smiling = len(smiles) > 0

                dominant = "desconocido"
                torso_bbox: tuple[float, float, float, float] | None = None
                try:
                    torso_x1 = max(0, int(x - fw * 0.6))
                    torso_x2 = min(w, int(x + fw * 1.6))
                    torso_y1 = min(h, y + fh)
                    torso_y2 = min(h, int(y + fh * 2.2))
                    if torso_y2 - torso_y1 < max(8, int(fh * 0.35)):
                        torso_y1 = max(0, h - max(8, fh))
                        torso_y2 = h
                    if torso_y2 > torso_y1 and torso_x2 > torso_x1:
                        torso = frame[torso_y1:torso_y2, torso_x1:torso_x2]
                        pixels = torso.reshape(-1, 3).astype(float)
                        visible = pixels.max(axis=1) > 30
                        clipped = pixels.min(axis=1) > 235
                        samples = pixels[visible & ~clipped]
                        if samples.size == 0:
                            samples = pixels
                        dominant = _classify_color(np.median(samples, axis=0))
                        torso_bbox = (
                            torso_x1 / w,
                            torso_y1 / h,
                            (torso_x2 - torso_x1) / w,
                            (torso_y2 - torso_y1) / h,
                        )
                except Exception:
                    pass

                return FaceVisualContext(
                    dominant_color=dominant,
                    smiling=smiling,
                    face_position=pos,
                    face_distance=dist,
                    lighting=light,
                    torso_bbox=torso_bbox,
                )

            ordered_faces = sorted(
                (
                    (int(face[0]), int(face[1]), int(face[2]), int(face[3]))
                    for face in faces
                ),
                key=lambda face: face[0],
            )
            face_contexts = tuple(_analyze_face(face) for face in ordered_faces)
            colors = [
                face.dominant_color
                for face in face_contexts
                if face.dominant_color != "desconocido"
            ]
            dominant = colors[0] if len(set(colors)) <= 1 and colors else "varios"

            return VisualContext(
                face_count=len(face_contexts),
                dominant_color=dominant,
                smiling=all(face.smiling for face in face_contexts),
                face_position=face_contexts[0].face_position,
                face_distance=face_contexts[0].face_distance,
                lighting=light,
                face_contexts=face_contexts,
            )

        return await loop.run_in_executor(None, _run)

    @staticmethod
    def _color_name(bgr: object) -> str:
        return _classify_color(bgr)

    async def extract_visual_data(self, frame_bgr: object) -> dict[str, object]:
        ctx = await self.analyze(frame_bgr)
        faces = await self.detect(frame_bgr)
        return {
            "context": ctx,
            "faces": faces,
        }


@dataclass
class ActivityHints:
    motion: str = "quieto"
    head_direction: str = "frente"
    likely_doing: str = "mirando"
    frame_diff_pct: float = 0.0
    face_moved: bool = False


def detect_activity(
    prev_frame: object | None,
    curr_frame: object,
    prev_ctx: VisualContext | None,
    curr_ctx: VisualContext,
) -> ActivityHints:
    import cv2
    import numpy as np

    hints = ActivityHints()

    if prev_frame is not None:
        try:
            p = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)  # type: ignore[call-overload]
            c = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)  # type: ignore[call-overload]
            h, w = p.shape[:2]
            diff = cv2.absdiff(p, c)
            diff_pct = float(np.count_nonzero(diff > 15)) / (h * w)
            hints.frame_diff_pct = diff_pct

            if diff_pct > 0.03:
                hints.motion = "movimiento"
            elif diff_pct > 0.005:
                hints.motion = "leve"
            else:
                hints.motion = "quieto"
        except Exception:
            pass

    if prev_ctx is not None and curr_ctx.face_count > 0 and prev_ctx.face_count > 0:
        if curr_ctx.face_position != prev_ctx.face_position:
            hints.head_direction = curr_ctx.face_position
            hints.face_moved = True

        if curr_ctx.face_distance != prev_ctx.face_distance:
            hints.face_moved = True

    if hints.motion == "quieto" and hints.head_direction == "frente" and curr_ctx.smiling:
        hints.likely_doing = "hablando"
    elif hints.motion == "leve" and hints.head_direction == "frente":
        hints.likely_doing = "escribiendo o usando el celular"
    elif hints.motion == "movimiento" and hints.face_moved:
        hints.likely_doing = "moviéndose o gesticulando"
    elif curr_ctx.face_count > 0 and hints.motion == "quieto":
        hints.likely_doing = "mirando fijamente"
    elif curr_ctx.face_count == 0 and prev_ctx is not None and prev_ctx.face_count > 0:
        hints.likely_doing = "saliendo del encuadre"

    return hints
