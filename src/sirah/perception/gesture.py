"""Pure MediaPipe-style gesture helpers; MediaPipe remains optional.

The gesture recognizer (M5) follows the YuNet pattern: a zero-dependency
pure core (classification, allowlist, canonicalization) plus an optional
adapter that imports MediaPipe. MediaPipe's canonical gesture categories
are kept, but only the allowlist survives to the evidence layer:
Open_Palm, Thumb_Up, Thumb_Down, Victory. Everything else is treated as
`None`/no-gesture so noise never reaches WorldState.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sirah.perception.evidence import RawObservation

# MediaPipe GestureRecognizer canonical category names that SIRAH consumes.
# A gesture outside this set is ignored by the evidence layer entirely.
GESTURE_ALLOWLIST = frozenset({"Open_Palm", "Thumb_Up", "Thumb_Down", "Victory"})

_GESTURE_VALUES = {
    "Open_Palm": "open_palm",
    "Thumb_Up": "thumb_up",
    "Thumb_Down": "thumb_down",
    "Victory": "victory",
}

# Acquisition window for gesture keys (seconds). A HELD gesture must still
# reach confirm_samples=2 — a single frame is never stable truth. MediaPipe
# hand recognition on edge hardware is real-time but NOT sample-locked: hand
# landmark dropout and classification confidence jitter mean two valid
# allowlisted detections of a maintained gesture can land more than the
# global confirm_window_s (0.5 s) apart, which resets the candidate and
# postpones confirmation for many seconds while the pose is actually held.
# This window only grants the second genuine observation enough time; it is
# gesture-specific via EvidenceHub(kind_overrides=...), so face/person keep
# the global policy. Derived from the expected live cadence (5-15 Hz
# inference -> 70-200 ms between feeds, plus dropout/confidence gaps) with a
# ~2-7x margin; tune per physical measurement if it is still too tight.
GESTURE_CONFIRM_WINDOW_S = 1.5


@dataclass(frozen=True)
class GestureCategory:
    """One MediaPipe classification entry: name + score in [0, 1]."""

    name: str
    score: float


@dataclass(frozen=True)
class Landmark:
    """One hand landmark in a normalized coordinate space.

    `x`/`y` in [0, 1] image coordinates; `z` is the approximate depth
    from the wrist (MediaPipe `NormalizedLandmark`) or a world-space
    metric value (MediaPipe `Landmark`), depending on which result field
    produced it. Preserved so M6 Wave can use hand geometry without a
    separate HandLandmarker.
    """

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HandGesture:
    """One recognized hand: allowlisted gesture, confidence and identity.

    `landmarks`/`world_landmarks` carry the raw MediaPipe 21-point hand
    geometry normalized at the adapter boundary (empty when the source
    does not provide them), so downstream layers never see vendor types.
    """

    gesture: str  # canonical value, e.g. "thumb_up" (not a MediaPipe category)
    confidence: float
    handedness: str  # "Left", "Right" or "Unknown"
    index: int  # 0-based hand index in the frame
    landmarks: tuple[Landmark, ...] = ()
    world_landmarks: tuple[Landmark, ...] = ()


@dataclass(frozen=True)
class RawHand:
    """What MediaPipe actually reported for one hand, allowlisted or not.

    Diagnostic only: the best category name/score before SIRAH's semantic
    allowlist is applied, so an operator can see WHY a category produced
    no observation (not in the allowlist). Never becomes behavior input.
    """

    index: int
    handedness: str
    category: str  # raw MediaPipe category, e.g. "Closed_Fist"
    confidence: float
    landmarks: tuple[Landmark, ...] = ()
    world_landmarks: tuple[Landmark, ...] = ()


@dataclass(frozen=True)
class GestureDetection:
    """One recognition pass: allowlisted hands plus everything MediaPipe saw.

    `hands` feeds the evidence layer (`gesture_observations`); `raw` is
    the full diagnostic view used by the preview to explain rejections.
    """

    hands: tuple[HandGesture, ...]
    raw: tuple[RawHand, ...]
    timestamp_ms: int


def canonical_value(category: str) -> str | None:
    """Map a MediaPipe category name to the canonical SIRAH value."""
    return _GESTURE_VALUES.get(category)


def is_allowed(category: str) -> bool:
    """True when the MediaPipe category is in the gesture allowlist."""
    return category in GESTURE_ALLOWLIST


def best_category(categories: Sequence[GestureCategory]) -> GestureCategory | None:
    """The highest-confidence category, or None when empty."""
    return max(categories, key=lambda category: category.score, default=None)


def classify_hands(
    hands: Sequence[Sequence[GestureCategory]],
    *,
    handedness: Sequence[str] | None = None,
    landmarks: Sequence[Sequence[Landmark]] | None = None,
    world_landmarks: Sequence[Sequence[Landmark]] | None = None,
) -> list[HandGesture]:
    """Map per-hand category lists to allowlisted hand gestures.

    `hands[i]` is the top-k classification list for hand i, already sorted
    by score by the recognizer. Only the best category of each hand is
    considered; non-allowlisted gestures yield no observation. When
    provided, `landmarks[i]`/`world_landmarks[i]` (21-point geometry) are
    attached to the matching hand so downstream layers keep the raw shape.
    """
    if handedness is None:
        handedness = ("Unknown",) * len(hands)
    observed: list[HandGesture] = []
    for index, categories in enumerate(hands):
        best = best_category(categories)
        if best is None:
            continue
        value = canonical_value(best.name)
        if value is None:
            continue
        observed.append(
            HandGesture(
                gesture=value,
                confidence=best.score,
                handedness=handedness[index] if index < len(handedness) else "Unknown",
                index=index,
                landmarks=tuple(landmarks[index]) if landmarks and index < len(landmarks) else (),
                world_landmarks=(
                    tuple(world_landmarks[index])
                    if world_landmarks and index < len(world_landmarks)
                    else ()
                ),
            )
        )
    return observed


def raw_hands(
    hands: Sequence[Sequence[GestureCategory]],
    *,
    handedness: Sequence[str] | None = None,
    landmarks: Sequence[Sequence[Landmark]] | None = None,
    world_landmarks: Sequence[Sequence[Landmark]] | None = None,
) -> list[RawHand]:
    """The full diagnostic view of one recognition pass, allowlist ignored.

    Every detected hand is reported with its best category (raw MediaPipe
    name), so the preview can explain why a gesture did NOT become a
    stable observation (e.g. `Closed_Fist` is simply not allowlisted).
    """
    if handedness is None:
        handedness = ("Unknown",) * len(hands)
    seen: list[RawHand] = []
    for index, categories in enumerate(hands):
        best = best_category(categories)
        if best is None:
            continue
        seen.append(
            RawHand(
                index=index,
                handedness=handedness[index] if index < len(handedness) else "Unknown",
                category=best.name,
                confidence=best.score,
                landmarks=tuple(landmarks[index]) if landmarks and index < len(landmarks) else (),
                world_landmarks=(
                    tuple(world_landmarks[index])
                    if world_landmarks and index < len(world_landmarks)
                    else ()
                ),
            )
        )
    return seen


def gesture_observations(
    hands: Sequence[HandGesture],
    *,
    observed_at: float,
    source: str = "mediapipe_gesture",
) -> list[RawObservation]:
    """Turn recognized gestures into evidence-layer raw observations.

    `track_id` is the handedness when known (stable across frames) and
    falls back to a positional hand id, so two hands of the same gesture
    confirm independently.
    """
    raws: list[RawObservation] = []
    for hand in hands:
        track_id = hand.handedness if hand.handedness != "Unknown" else f"hand_{hand.index}"
        raws.append(
            RawObservation(
                source=source,
                kind="gesture",
                value=hand.gesture,
                confidence=hand.confidence,
                observed_at=observed_at,
                track_id=track_id,
            )
        )
    return raws