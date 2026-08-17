"""MediaPipe GestureRecognizer adapter (M5); MediaPipe stays optional.

Mirrors the YuNet adapter shape: the class is importable without the
heavy dependency, model loading is explicit and local, and the
recognizer factory is injectable for deterministic tests. Detection uses
MediaPipe's VIDEO running mode (`recognize_for_video`) so the adapter is
a plain synchronous call on the caller's loop, matching SIRAH's
latest-frame pipeline: the recognizer is never a background worker here.
Output is normalized to `HandGesture` values; the evidence layer decides
what becomes stable state.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Protocol

from sirah.perception.contracts import Frame
from sirah.perception.gesture import (
    GestureCategory,
    HandGesture,
    classify_hands,
)


class _GestureCategory(Protocol):
    """Minimal MediaPipe `Classification` shape (name + score)."""

    category_name: str
    score: float


class _RecognizerResult(Protocol):
    """Minimal MediaPipe `GestureRecognizerResult` shape used by SIRAH."""

    gestures: Sequence[Sequence[_GestureCategory]]
    handedness: Sequence[Sequence[_GestureCategory]]


class _Recognizer(Protocol):
    def recognize_for_video(self, image: object, timestamp_ms: int) -> _RecognizerResult: ...


class MediaPipeGestureRecognizer:
    """MediaPipe Tasks GestureRecognizer in VIDEO mode, normalized to
    `HandGesture`. Requires the `gesture` extra and a verified model
    asset (see `sirah-models gesture`).
    """

    def __init__(
        self,
        model_path: Path,
        *,
        recognizer_factory: Callable[[Path], _Recognizer] | None = None,
        num_hands: int = 2,
        min_hand_detection_confidence: float = 0.5,
        min_hand_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"gesture model not found: {model_path}")
        if num_hands < 1:
            raise ValueError("num_hands must be at least one")
        factory = recognizer_factory or partial(
            _mediapipe_recognizer,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._recognizer: _Recognizer = factory(model_path)
        self._last_ts_ms = 0

    def recognize(self, frame: Frame) -> list[HandGesture]:
        """Detect allowlisted hand gestures in the frame (synchronous).

        `frame.payload` must be a numpy BGR image. Returns an empty list
        for frames without a payload or without a recognized gesture.
        """
        payload = frame.payload
        if payload is None:
            return []
        # VIDEO mode requires monotonically increasing timestamps; the
        # adapter guarantees it even if the loop stalls between frames.
        ts_ms = self._next_ts_ms()
        result = self._recognizer.recognize_for_video(_rgb(payload), ts_ms)
        return classify_hands(
            [
                [GestureCategory(category.category_name, category.score) for category in categories]
                for categories in result.gestures
            ],
            handedness=[
                labels[0].category_name for labels in result.handedness
            ],
        )

    def _next_ts_ms(self) -> int:
        now_ms = _monotonic_ms()
        if now_ms <= self._last_ts_ms:
            now_ms = self._last_ts_ms + 1
        self._last_ts_ms = now_ms
        return now_ms


def _monotonic_ms() -> int:
    import time

    return int(time.monotonic() * 1000)


def _rgb(bgr: object) -> object:
    """BGR numpy frame → RGB numpy array (no OpenCV needed for the flip)."""
    return bgr[:, :, ::-1]  # type: ignore[index]


def _mediapipe_recognizer(
    model_path: Path,
    *,
    num_hands: int,
    min_hand_detection_confidence: float,
    min_hand_presence_confidence: float,
    min_tracking_confidence: float,
) -> _Recognizer:
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError('install gesture support: pip install -e ".[gesture]"') from exc

    base_options = mp.tasks.BaseOptions(model_asset_path=str(model_path))
    options = mp.tasks.vision.GestureRecognizerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=min_hand_detection_confidence,
        min_hand_presence_confidence=min_hand_presence_confidence,
        min_tracking_confidence=min_tracking_confidence,
    )
    return mp.tasks.vision.GestureRecognizer.create_from_options(options)