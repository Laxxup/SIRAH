"""MediaPipe GestureRecognizer adapter (M5); MediaPipe stays optional.

Mirrors the YuNet adapter shape: the class is importable without the
heavy dependency, model loading is explicit and local, and the
recognizer factory is injectable for deterministic tests.

Mode decision (M5.1): VIDEO running mode (`recognize_for_video`) is kept
for BOTH live camera and replay, and the synchronous inference is always
run off the asyncio event loop by a dedicated worker (see
`gesture_worker.GestureWorker`). Rationale:

- VIDEO returns a complete result for every processed frame. An empty
  `gestures` list unambiguously means "no hand detected", so absence can
  advance the evidence layer's release/TTL semantics directly.
- LIVE_STREAM (`recognize_async`) may intentionally drop input frames and
  delivers results asynchronously on MediaPipe's own dispatcher thread.
  A dropped frame must NOT be interpreted as "no hand", which forces a
  no-result/release distinction the evidence layer cannot see. That
  hazard does not exist in VIDEO mode, and MediaPipe never drops frames
  for us.
- The FrameBroker already provides the freshness > completeness policy:
  the worker pulls the newest frame from its subscriber slot, so a slow
  detector skips intermediate frames (latest frame wins) without any
  MediaPipe-side dropping.

The recognizer expects `mp.Image` objects; SIRAH frames are BGR numpy
arrays, so the adapter converts BGR -> contiguous SRGB numpy at the
boundary and the MediaPipe recognizer wraps it into an `mp.Image`. The
shared broker frame is never mutated in place.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Protocol

from sirah.perception.contracts import Frame
from sirah.perception.gesture import (
    GestureCategory,
    GestureDetection,
    HandGesture,
    Landmark,
    classify_hands,
    raw_hands,
)


class _GestureCategory(Protocol):
    """Minimal MediaPipe `Classification` shape (name + score)."""

    category_name: str
    score: float


class _Landmark3D(Protocol):
    """Minimal MediaPipe landmark shape (x, y, z floats)."""

    x: float
    y: float
    z: float


class _RecognizerResult(Protocol):
    """Minimal MediaPipe `GestureRecognizerResult` shape used by SIRAH."""

    gestures: Sequence[Sequence[_GestureCategory]]
    handedness: Sequence[Sequence[_GestureCategory]]
    hand_landmarks: Sequence[Sequence[_Landmark3D]]
    hand_world_landmarks: Sequence[Sequence[_Landmark3D]]


class _Recognizer(Protocol):
    def recognize_for_video(self, image: object, timestamp_ms: int) -> _RecognizerResult: ...

    def close(self) -> None: ...


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
        """Allowlisted hand gestures in the frame (synchronous).

        `frame.payload` must be a numpy BGR image. Returns an empty list
        for frames without a payload or without a recognized gesture.
        """
        return list(self.recognize_detailed(frame).hands)

    def recognize_detailed(self, frame: Frame) -> GestureDetection:
        """Full recognition result: allowlisted hands plus raw diagnostic
        hands (allowlist ignored) and the geometry MediaPipe reported."""
        payload = frame.payload
        if payload is None:
            return GestureDetection(hands=(), raw=(), timestamp_ms=self._next_ts_ms())
        # VIDEO mode requires monotonically increasing timestamps; the
        # adapter guarantees it even if the loop stalls between frames.
        ts_ms = self._next_ts_ms()
        result = self._recognizer.recognize_for_video(_rgb(payload), ts_ms)
        categories = [
            [GestureCategory(category.category_name, category.score) for category in categories]
            for categories in result.gestures
        ]
        handedness = [labels[0].category_name for labels in result.handedness]
        landmarks = [_landmarks(hand) for hand in result.hand_landmarks]
        world_landmarks = [_landmarks(hand) for hand in result.hand_world_landmarks]
        hands = classify_hands(
            categories,
            handedness=handedness,
            landmarks=landmarks,
            world_landmarks=world_landmarks,
        )
        raw = raw_hands(
            categories,
            handedness=handedness,
            landmarks=landmarks,
            world_landmarks=world_landmarks,
        )
        return GestureDetection(
            hands=tuple(hands), raw=tuple(raw), timestamp_ms=ts_ms
        )

    def close(self) -> None:
        """Release the MediaPipe recognizer (native resources)."""
        self._recognizer.close()

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
    """BGR numpy frame -> contiguous SRGB numpy array.

    `[::-1]` yields a non-contiguous view; the copy guarantees MediaPipe
    receives a plain SRGB buffer and the shared broker frame is never
    mutated or aliased.
    """
    import numpy as np

    return np.ascontiguousarray(bgr[:, :, ::-1])  # type: ignore[index]


def _landmarks(hand: Sequence[_Landmark3D]) -> tuple[Landmark, ...]:
    return tuple(Landmark(p.x, p.y, p.z) for p in hand)


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
    recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)
    return _MpImageRecognizer(recognizer, mp.ImageFormat.SRGB)


class _MpImageRecognizer:
    """Wraps a MediaPipe recognizer so SIRAH passes numpy SRGB frames.

    The adapter converts BGR -> contiguous SRGB numpy; this wrapper
    packages that array into the `mp.Image` MediaPipe actually requires
    (`recognize_for_video` expects an `mp.Image`, not a raw array).
    """

    def __init__(self, recognizer: object, image_format: object) -> None:
        self._recognizer = recognizer
        self._image_format = image_format

    def recognize_for_video(self, image: object, timestamp_ms: int) -> _RecognizerResult:
        import mediapipe as mp

        mp_image = mp.Image(image_format=self._image_format, data=image)
        return self._recognizer.recognize_for_video(mp_image, timestamp_ms)  # type: ignore[attr-defined]

    def close(self) -> None:
        self._recognizer.close()  # type: ignore[attr-defined]