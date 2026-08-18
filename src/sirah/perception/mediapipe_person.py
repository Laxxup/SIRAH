"""MediaPipe ObjectDetector adapter for person detection (M6).

Mirrors the `mediapipe_gesture` adapter shape exactly:

- importable without the heavy dependency (mediapipe stays optional);
- model loading is explicit and local (verified via `sirah-models person`);
- VIDEO running mode (`detect_for_video`) — same decision as the
  GestureRecognizer: a complete result per processed frame, no dropped
  callbacks, freshness controlled by the FrameBroker (latest-frame wins);
- the detector factory is injectable for deterministic tests;
- BGR frames convert to contiguous SRGB numpy at the boundary; the shared
  broker frame is never mutated.

The adapter filters the COCO "person" class (label 0 of the 80-class
EfficientDet-Lite0 model) and normalizes MediaPipe's pixel bbox to SIRAH's
canonical NON-mirrored normalized coordinates. Boxes fully outside the
frame are rejected at the boundary (invalid boxes are not observations);
boxes spilling a few pixels past the edge stay canonical and truthful —
the renderer clips for presentation only.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Protocol

from sirah.perception.contracts import Frame
from sirah.perception.person import PersonDetection

# COCO 80-class label for EfficientDet-Lite0
_PERSON_LABEL = "person"
_DETECTOR_PROVENANCE = "mediapipe_efficientdet_lite0"


class _Category(Protocol):
    """Minimal MediaPipe `Category` shape (label + score)."""

    category_name: str
    score: float


class _BoundingBox(Protocol):
    """Minimal MediaPipe `BoundingBox` shape (pixel geometry)."""

    origin_x: int
    origin_y: int
    width: int
    height: int


class _Detection(Protocol):
    """Minimal MediaPipe `Detection` shape consumed by SIRAH."""

    categories: Sequence[_Category]
    bounding_box: _BoundingBox


class _DetectorResult(Protocol):
    detections: Sequence[_Detection]


class _Detector(Protocol):
    def detect_for_video(self, image: object, timestamp_ms: int) -> _DetectorResult: ...

    def close(self) -> None: ...


class MediaPipePersonDetector:
    """MediaPipe Tasks ObjectDetector in VIDEO mode, person-class filtered.

    Requires mediapipe (the `gesture` extra) and a verified model asset
    (see `sirah-models person`).
    """

    def __init__(
        self,
        model_path: Path,
        *,
        detector_factory: Callable[[Path], _Detector] | None = None,
        score_threshold: float = 0.3,
        max_results: int = 20,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"person model not found: {model_path}")
        if not 0.0 <= score_threshold <= 1.0:
            raise ValueError("score_threshold must be normalized")
        if max_results < 1:
            raise ValueError("max_results must be positive")
        factory = detector_factory or partial(
            _mediapipe_detector,
            score_threshold=score_threshold,
            max_results=max_results,
        )
        self._detector: _Detector = factory(model_path)
        self._last_ts_ms = 0
        self._clock = clock or _monotonic

    def detect_persons(self, frame: Frame) -> tuple[PersonDetection, ...]:
        """Person detections in one frame (canonical normalized bboxes).

        Returns an empty tuple for frames without a payload or without any
        person detection. Timestamps are guaranteed monotonically
        increasing (VIDEO-mode requirement) even if the loop stalls.
        """
        payload = frame.payload
        if payload is None:
            return ()
        height, width = _dims(payload)
        if width <= 0 or height <= 0:
            return ()
        ts_ms = self._next_ts_ms()
        result = self._detector.detect_for_video(_rgb(payload), ts_ms)
        produced_at = self._clock()
        detections: list[PersonDetection] = []
        for det in result.detections:
            if not det.categories:
                continue
            category = det.categories[0]
            if category.category_name != _PERSON_LABEL:
                continue
            box = det.bounding_box
            x = box.origin_x / width
            y = box.origin_y / height
            w = box.width / width
            h = box.height / height
            try:
                detections.append(
                    PersonDetection(
                        x=x,
                        y=y,
                        width=w,
                        height=h,
                        confidence=category.score,
                        source_frame_index=frame.index,
                        captured_at=frame.captured_at,
                        produced_at=produced_at,
                        detector=_DETECTOR_PROVENANCE,
                    )
                )
            except ValueError:
                # defensive: a non-finite / non-normalized / off-frame box is
                # not an observation; skip it, never mutate or clamp core values.
                continue
        return tuple(detections)

    def close(self) -> None:
        """Release the MediaPipe detector (native resources)."""
        self._detector.close()

    def _next_ts_ms(self) -> int:
        now_ms = int(self._clock() * 1000)
        if now_ms <= self._last_ts_ms:
            now_ms = self._last_ts_ms + 1
        self._last_ts_ms = now_ms
        return now_ms


def _monotonic() -> float:
    import time

    return time.monotonic()


def _dims(payload: object) -> tuple[int, int]:
    shape = getattr(payload, "shape", None)
    if not isinstance(shape, tuple) or len(shape) < 2:
        return 0, 0
    height, width = shape[0], shape[1]
    return int(height), int(width)


def _rgb(bgr: object) -> object:
    """BGR numpy frame -> contiguous SRGB numpy array (never aliased)."""
    import numpy as np

    return np.ascontiguousarray(bgr[:, :, ::-1])  # type: ignore[index]


def _mediapipe_detector(
    model_path: Path,
    *,
    score_threshold: float,
    max_results: int,
) -> _Detector:
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError(
            "install person detection support: pip install -e \".[gesture]\""
        ) from exc
    base_options = mp.tasks.BaseOptions(model_asset_path=str(model_path))
    options = mp.tasks.vision.ObjectDetectorOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        score_threshold=score_threshold,
        max_results=max_results,
    )
    detector = mp.tasks.vision.ObjectDetector.create_from_options(options)
    return _MpImageDetector(detector, mp.ImageFormat.SRGB)


class _MpImageDetector:
    """Wraps a MediaPipe detector so SIRAH passes numpy SRGB frames."""

    def __init__(self, detector: object, image_format: object) -> None:
        self._detector = detector
        self._image_format = image_format

    def detect_for_video(self, image: object, timestamp_ms: int) -> _DetectorResult:
        import mediapipe as mp

        mp_image = mp.Image(image_format=self._image_format, data=image)
        return self._detector.detect_for_video(mp_image, timestamp_ms)  # type: ignore[attr-defined]

    def close(self) -> None:
        self._detector.close()  # type: ignore[attr-defined]