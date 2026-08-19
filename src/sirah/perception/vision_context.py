"""Vision V1 (M8.1): turn stable perception facts into a compact AI context.

Bridge between the evidence layer and the conversation AI. Perception
already produces `StableState`s (face present, tracked persons, allowlisted
gestures) through `EvidenceHub`; this module formats the CURRENT FRESH
subset into a few compact semantic lines the LLM can ground answers on,
and keeps a bounded log of RECENT edge events.

Rules enforced here:

- conversation never sees raw detector output: no bounding boxes, no
  landmarks, no numpy arrays, no model names, no confidence dumps;
- stale perception is never current truth: only `StableState`s whose TTL
  has not lapsed (`PerceptionFacts.fresh`) enter the CURRENT section;
- CURRENT (fresh facts) is kept separate from RECENT EVENT (bounded
  event history with age) and from UNKNOWN (vision unavailable → None);
- session-local track ids are reported only as "persona #N", never as
  a human identity; several tracks are listed separately, never fused.

The `VisionContextProvider` stores the latest immutable snapshot the
conversation may read synchronously; perception never waits for the LLM.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import hypot, isfinite

from sirah.perception.contracts import GazeTarget
from sirah.perception.evidence import RawObservation, StableEvent
from sirah.perception.person import ObservedScene
from sirah.perception.world_state import PerceptionFacts

# A track whose box-center speed is at or above this many normalized
# units per second is described as moving; below, as stationary. The
# velocity estimate already lives on `PersonTrack`; this is only a
# conservative binary interpretation for the AI context.
MOTION_SPEED_THRESHOLD = 0.1

# Vision is "available" only while the evidence layer has ticked within
# this window; afterwards the context is omitted (vision unknown), so a
# dead camera is never reported as "nobody there".
DEFAULT_AVAILABILITY_WINDOW_S = 5.0
# Events older than this are not part of the RECENT section.
DEFAULT_RECENT_WINDOW_S = 15.0
# Upper bound on RECENT event lines (bounded token cost).
DEFAULT_RECENT_LIMIT = 8

_KIND_FACE = "face"
_KIND_PERSON = "person"
_KIND_MOTION = "motion"
_KIND_GESTURE = "gesture"

_FACE_TRACK_ID = "primary"


def face_observation(target: GazeTarget | None, *, now: float) -> RawObservation:
    """YuNet attended face → evidence observation (kind="face").

    Confidence 0.0 (no face) surfaces as a below-confidence rejection so
    the diagnostic preview keeps explaining why nothing became stable.
    """
    confidence = target.confidence if target is not None else 0.0
    return RawObservation(
        source="yunet",
        kind=_KIND_FACE,
        value="present",
        confidence=confidence,
        observed_at=now,
        track_id=_FACE_TRACK_ID,
    )


def person_observations(scene: ObservedScene | None, *, now: float) -> tuple[RawObservation, ...]:
    """ObservedScene → evidence observations for every CURRENTLY observed track.

    Each active (tentative + confirmed) track contributes:

    - kind="person", value="present" (the temporary person is here now);
    - kind="motion", value="moving"|"stationary" only when the tracker has
      a velocity estimate (existing `PersonTrack` data, no new subsystem).

    TEMPORARILY_LOST / EXPIRED tracks produce nothing: absence is handled
    by the evidence layer's own release/TTL sweep. Track ids are
    session-local labels ("track_N"), never identities.
    """
    if scene is None:
        return ()
    observations: list[RawObservation] = []
    for track in scene.active:
        track_id = f"track_{track.track_id}"
        observations.append(
            RawObservation(
                source="person_tracker",
                kind=_KIND_PERSON,
                value="present",
                confidence=track.confidence,
                observed_at=now,
                track_id=track_id,
            )
        )
        if track.velocity is not None:
            vx, vy = track.velocity
            moving = hypot(vx, vy) >= MOTION_SPEED_THRESHOLD
            observations.append(
                RawObservation(
                    source="person_tracker",
                    kind=_KIND_MOTION,
                    value="moving" if moving else "stationary",
                    confidence=track.confidence,
                    observed_at=now,
                    track_id=track_id,
                )
            )
    return tuple(observations)


def _track_number(track_id: str | None) -> int | None:
    """The numeric part of a "track_N" id, or None for non-person tracks."""
    if track_id is None or not track_id.startswith("track_"):
        return None
    try:
        return int(track_id.split("_", 1)[1])
    except ValueError:
        return None


@dataclass(frozen=True)
class RecentVisualEvent:
    """One edge event retained for the RECENT section (bounded, with age)."""

    event: str  # e.g. "person_present_confirmed"
    kind: str
    value: str
    track_id: str | None
    observed_at: float

    def __post_init__(self) -> None:
        if not self.event or not self.kind or not self.value:
            raise ValueError("event, kind and value must be non-empty")
        if not isfinite(self.observed_at):
            raise ValueError("observed_at must be finite")


@dataclass(frozen=True)
class VisionContext:
    """Compact, temporally-honest visual context for the conversation AI."""

    available: bool
    current: tuple[str, ...] = ()
    recent: tuple[str, ...] = ()

    @property
    def text(self) -> str | None:
        """The compact block to inject into the conversation context.

        None when vision is unavailable (the AI simply proceeds without
        visual grounding). A fresh-but-empty scene is marked explicitly so
        the model does not hallucinate presence.
        """
        if not self.available:
            return None
        lines: list[str] = []
        if self.current:
            lines.append("VISIÓN ACTUAL:")
            lines.extend(f"- {line}" for line in self.current)
        if self.recent:
            lines.append("EVENTOS VISUALES RECIENTES:")
            lines.extend(f"- {line}" for line in self.recent)
        if not lines:
            lines.append("VISIÓN ACTUAL:")
            lines.append("- Sin información visual fresca.")
        return "\n".join(lines)


def format_vision_context(
    facts: PerceptionFacts | None,
    recent: Sequence[RecentVisualEvent],
    *,
    now: float,
    availability_window_s: float = DEFAULT_AVAILABILITY_WINDOW_S,
    recent_window_s: float = DEFAULT_RECENT_WINDOW_S,
    recent_limit: int = DEFAULT_RECENT_LIMIT,
    perceived: bool = False,
) -> VisionContext:
    """Format the latest snapshot into a compact, freshness-aware context.

    `now` is the monotonic format time; a fact is CURRENT only while its
    own TTL has not lapsed. Recent events are bounded both by age
    (`recent_window_s`) and count (`recent_limit`). `perceived` records
    that the pipeline has at least once confirmed a person/face/gesture:
    without it an empty snapshot would be misread as freshly-confirmed
    absence ("nobody there") when we have no evidence either way.
    """
    if not isfinite(now):
        raise ValueError("now must be finite")
    if facts is None or now - facts.observed_at > availability_window_s:
        return VisionContext(available=False)
    return VisionContext(
        available=True,
        current=_current_lines(facts, now, perceived=perceived),
        recent=_recent_lines(recent, now, recent_window_s, recent_limit),
    )


def _current_lines(facts: PerceptionFacts, now: float, *, perceived: bool) -> tuple[str, ...]:
    fresh = facts.fresh(now)
    person_states = [state for state in fresh.states if state.kind == _KIND_PERSON]
    face_state = fresh.state_of(_KIND_FACE, _FACE_TRACK_ID)
    gesture_states = [state for state in fresh.states if state.kind == _KIND_GESTURE]
    motion_states = [state for state in fresh.states if state.kind == _KIND_MOTION]

    lines: list[str] = []
    if person_states:
        numbers = sorted(number for state in person_states if (number := _track_number(state.track_id)) is not None)
        label = "Persona visible:" if len(numbers) == 1 else "Personas visibles:"
        lines.append(f"{label} {', '.join(f'#{n}' for n in numbers)}.")
    elif face_state is None and not gesture_states and perceived:
        # absence is freshly confirmed by the sweeping evidence layer
        lines.append("No hay personas visibles.")

    for state in sorted(
        motion_states, key=lambda s: _track_number(s.track_id) or -1
    ):
        number = _track_number(state.track_id)
        if number is None:
            continue
        description = "en movimiento" if state.value == "moving" else "quieta"
        lines.append(f"Persona #{number} está {description}.")

    if face_state is not None:
        lines.append("Un rostro está visible.")

    gesture_counts: dict[str, int] = {}
    for state in gesture_states:
        gesture_counts[state.value] = gesture_counts.get(state.value, 0) + 1
    for value in sorted(gesture_counts):
        count = gesture_counts[value]
        if count == 1:
            lines.append(f"Gesto: {value}.")
        else:
            lines.append(f"Gesto: {value} ({count} manos).")
    return tuple(lines)


def _recent_lines(
    recent: Sequence[RecentVisualEvent],
    now: float,
    recent_window_s: float,
    recent_limit: int,
) -> tuple[str, ...]:
    fresh = [
        event
        for event in recent
        if event.kind != _KIND_MOTION and now - event.observed_at <= recent_window_s
    ]
    fresh.sort(key=lambda event: event.observed_at, reverse=True)
    return tuple(
        _format_recent_event(event, now - event.observed_at)
        for event in fresh[:recent_limit]
    )


def _format_recent_event(event: RecentVisualEvent, age: float) -> str:
    number = _track_number(event.track_id)
    if event.event == "person_present_confirmed" and number is not None:
        return f"Persona #{number} entró hace {age:.1f}s."
    if event.event == "person_present_released" and number is not None:
        return f"Persona #{number} salió hace {age:.1f}s."
    if event.event == "face_present_confirmed":
        return f"Un rostro apareció hace {age:.1f}s."
    if event.event == "face_present_released":
        return f"El rostro dejó de verse hace {age:.1f}s."
    if event.kind == _KIND_GESTURE and event.event.endswith("_confirmed"):
        return f"Gesto {event.value} detectado hace {age:.1f}s."
    if event.kind == _KIND_GESTURE and event.event.endswith("_released"):
        return f"El gesto {event.value} terminó hace {age:.1f}s."
    if number is not None:
        return f"Evento {event.event} (persona #{number}) hace {age:.1f}s."
    return f"Evento {event.event} hace {age:.1f}s."


class VisionContextProvider:
    """Holds the latest immutable snapshot for synchronous conversation reads.

    The vision pipeline feeds `observe()` on every evidence tick;
    conversation calls `text()` (cheap, non-blocking) per turn. Stale
    snapshots degrade gracefully: when the pipeline stops ticking past
    `availability_window_s`, `text()` returns None.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_recent: int = DEFAULT_RECENT_LIMIT,
        recent_window_s: float = DEFAULT_RECENT_WINDOW_S,
        availability_window_s: float = DEFAULT_AVAILABILITY_WINDOW_S,
    ) -> None:
        if max_recent < 1:
            raise ValueError("max_recent must be positive")
        self._clock = clock
        self._max_recent = max_recent
        self._recent_window_s = recent_window_s
        self._availability_window_s = availability_window_s
        self._facts: PerceptionFacts | None = None
        self._recent: deque[RecentVisualEvent] = deque(maxlen=max_recent)
        self._perceived = False

    def observe(
        self,
        facts: PerceptionFacts,
        events: Sequence[StableEvent],
        *,
        now: float,
    ) -> None:
        """Store the latest snapshot and retain the tick's edge events."""
        self._facts = facts
        for event in events:
            self._recent.append(
                RecentVisualEvent(
                    event=event.event,
                    kind=event.kind,
                    value=event.value,
                    track_id=event.track_id,
                    observed_at=event.observed_at,
                )
            )
            if event.kind in (_KIND_PERSON, _KIND_FACE, _KIND_GESTURE):
                self._perceived = True
        if any(
            state.kind in (_KIND_PERSON, _KIND_FACE, _KIND_GESTURE)
            for state in facts.states
        ):
            self._perceived = True

    def snapshot(self, *, now: float) -> VisionContext:
        """The vision context at `now` (current freshness vs recent events)."""
        return format_vision_context(
            self._facts,
            tuple(self._recent),
            now=now,
            availability_window_s=self._availability_window_s,
            recent_window_s=self._recent_window_s,
            recent_limit=self._max_recent,
            perceived=self._perceived,
        )

    def text(self) -> str | None:
        """The compact context block, or None when vision is unavailable."""
        return self.snapshot(now=self._clock()).text