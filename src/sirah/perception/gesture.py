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


@dataclass(frozen=True)
class GestureCategory:
    """One MediaPipe classification entry: name + score in [0, 1]."""

    name: str
    score: float


@dataclass(frozen=True)
class HandGesture:
    """One recognized hand: allowlisted gesture, confidence and identity."""

    gesture: str  # canonical value, e.g. "thumb_up" (not a MediaPipe category)
    confidence: float
    handedness: str  # "Left", "Right" or "Unknown"
    index: int  # 0-based hand index in the frame


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
) -> list[HandGesture]:
    """Map per-hand category lists to allowlisted hand gestures.

    `hands[i]` is the top-k classification list for hand i, already sorted
    by score by the recognizer. Only the best category of each hand is
    considered; non-allowlisted gestures yield no observation.
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
            )
        )
    return observed


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