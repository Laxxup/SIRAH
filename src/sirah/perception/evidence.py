"""Evidence layer (M2): turn noisy ML outputs into stable robot knowledge.

Architecture rule: RAW PERCEPTION MUST NEVER DIRECTLY TRIGGER PHYSICAL OR
CONVERSATIONAL SIDE EFFECTS. Model outputs are observations, not
authority. Every source (YuNet faces, MediaPipe gestures, objects, future
audio direction) emits `RawObservation`s that land HERE, are confirmed
temporally, and only then become `StableState` / `StableEvent` that
behavior and conversation may consume.

Design goals:
- generic over source/kind/value, so faces, gestures, objects and future
  modalities share one mechanism (no per-model frameworks);
- pure and deterministic: the state machines below are synchronous,
  clock-injected and fully unit-testable without hardware;
- edge-triggered: persistent STATE never floods events; transitions
  (NONE -> VALUE, VALUE -> NONE, VALUE_A -> VALUE_B) emit one-shot EVENTS
  with a cooldown;
- explicit temporal validity: every StableState carries observed_at /
  confirmed_at / expires_at so consumers can tell fresh from stale.

Semantics:
- STATE  e.g. PERSON_VISIBLE, OPEN_PALM, PHONE_VISIBLE (persistent).
- EVENT  e.g. PERSON_ENTERED, THUMB_UP_CONFIRMED, PERSON_LEFT (one-shot).
  Holding a thumb up for 5 seconds confirms ONCE, not per frame.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import TypedDict, Unpack


def _isfinite_or_raise(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


class RejectionReason(str, Enum):
    """Why an observation did not become stable (for diagnostics)."""

    BELOW_CONFIDENCE = "below_confidence"
    SWITCH_PENDING = "switch_pending"  # hysteresis: a stable value exists
    COOLDOWN = "cooldown"  # duplicate event suppressed within cooldown


@dataclass(frozen=True)
class RawObservation:
    """One model output, normalized at the boundary (no vendor types).

    `source` names the producer ("yunet", "gesture", "yolo", ...), `kind`
    the semantic family ("person", "gesture", "object"), `value` the
    concrete observation ("present", "thumb_up", "bottle"), `confidence`
    the model's score in [0, 1] and `track_id` an optional entity key
    (e.g. a hand or object track) so multiple entities of the same kind
    do not collide. `observed_at` is a monotonic clock timestamp.
    """

    source: str
    kind: str
    value: str
    confidence: float
    observed_at: float
    track_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source or not self.kind or not self.value:
            raise ValueError("source, kind and value must be non-empty")
        _isfinite_or_raise("observed_at", self.observed_at)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")

    @property
    def key(self) -> tuple[str, str | None]:
        """Identity of the entity this observation refers to."""
        return (self.kind, self.track_id)


@dataclass(frozen=True)
class StableState:
    """A confirmed, persistent fact (edge-confirmed, then held)."""

    kind: str
    value: str
    confidence: float
    observed_at: float  # last time the value was observed (refreshed)
    confirmed_at: float  # first time the value became stable
    expires_at: float | None  # observed_at + ttl; None = never expires
    track_id: str | None = None

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.kind, self.track_id)

    def is_stale(self, now: float) -> bool:
        """True when the fact is older than its TTL (not current truth)."""
        return self.expires_at is not None and now > self.expires_at

    def __post_init__(self) -> None:
        _isfinite_or_raise("observed_at", self.observed_at)
        _isfinite_or_raise("confirmed_at", self.confirmed_at)
        if self.confirmed_at > self.observed_at:
            raise ValueError("confirmed_at must not be after observed_at")
        if self.expires_at is not None:
            _isfinite_or_raise("expires_at", self.expires_at)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")


@dataclass(frozen=True)
class StableEvent:
    """One-shot, edge-triggered transition (duplicates suppressed)."""

    kind: str
    value: str
    event: str  # e.g. "gesture_thumb_up_confirmed" or "person_present_released"
    observed_at: float
    confidence: float
    track_id: str | None = None

    def __post_init__(self) -> None:
        _isfinite_or_raise("observed_at", self.observed_at)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized")


@dataclass(frozen=True)
class RejectedObservation:
    """A raw observation that did not become stable, and why."""

    raw: RawObservation
    reason: RejectionReason


@dataclass(frozen=True)
class PendingConfirmation:
    """A candidate value accumulating confirmation samples (diagnostic)."""

    kind: str
    track_id: str | None
    value: str
    confirm_count: int
    confirm_samples: int
    observed_at: float


@dataclass(frozen=True)
class EvidenceUpdate:
    """Result of feeding one observation to one key's filter."""

    state: StableState | None  # the key's stable state after this tick
    events: tuple[StableEvent, ...] = ()
    rejected: tuple[RejectedObservation, ...] = ()
    pending: PendingConfirmation | None = None


@dataclass(frozen=True)
class EvidenceSnapshot:
    """Whole-evidence view after one tick (all keys)."""

    states: tuple[StableState, ...] = ()
    events: tuple[StableEvent, ...] = ()
    rejected: tuple[RejectedObservation, ...] = ()
    pending: tuple[PendingConfirmation, ...] = ()

    def event_values(self) -> tuple[str, ...]:
        """Emitted event names, e.g. ("gesture_thumb_up_confirmed",)."""
        return tuple(event.event for event in self.events)

    def state_values(self) -> tuple[str, ...]:
        """Stable values, e.g. ("present", "open_palm")."""
        return tuple(state.value for state in self.states)


def _event_name(kind: str, value: str, *, released: bool) -> str:
    suffix = "released" if released else "confirmed"
    return f"{kind}_{value}_{suffix}"


class EvidenceFilterParams(TypedDict, total=False):
    """Overridable `EvidenceFilter` parameters for a whole hub or a kind."""

    min_confidence: float
    confirm_samples: int
    confirm_window_s: float | None
    release_window_s: float | None
    ttl_s: float | None
    cooldown_s: float
    hysteresis_conf: float


class EvidenceFilter:
    """Per-key (kind, track_id) stability state machine.

    Confirms a value after `confirm_samples` consecutive observations
    within `confirm_window_s`, holds it through brief absence
    (`release_window_s` grace), releases it (edge event) once it stops
    being observed or its TTL (`ttl_s`) lapses, and switches to a
    competing value only after the same confirmation (hysteresis), with
    an optional `hysteresis_conf` confidence delta.
    """

    def __init__(
        self,
        kind: str,
        track_id: str | None = None,
        *,
        min_confidence: float = 0.5,
        confirm_samples: int = 2,
        confirm_window_s: float | None = 0.5,
        release_window_s: float | None = 1.0,
        ttl_s: float | None = 3.0,
        cooldown_s: float = 2.0,
        hysteresis_conf: float = 0.0,
    ) -> None:
        if not kind:
            raise ValueError("kind must be non-empty")
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be normalized")
        if confirm_samples < 1:
            raise ValueError("confirm_samples must be at least one")
        for name, value in (
            ("confirm_window_s", confirm_window_s),
            ("release_window_s", release_window_s),
            ("ttl_s", ttl_s),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        if cooldown_s < 0:
            raise ValueError("cooldown_s must not be negative")
        if not 0.0 <= hysteresis_conf <= 1.0:
            raise ValueError("hysteresis_conf must be normalized")
        self.kind = kind
        self.track_id = track_id
        self.min_confidence = min_confidence
        self.confirm_samples = confirm_samples
        self.confirm_window_s = confirm_window_s
        self.release_window_s = release_window_s
        self.ttl_s = ttl_s
        self.cooldown_s = cooldown_s
        self.hysteresis_conf = hysteresis_conf
        self.reset()

    def reset(self) -> None:
        """Drop all state: the next observation restarts acquisition."""
        self._value: str | None = None
        self._last_confidence: float | None = None
        self._last_observed_at: float | None = None
        self._stable_since: float | None = None
        self._candidate_value: str | None = None
        self._candidate_count = 0
        self._candidate_first_at: float | None = None
        self._candidate_last_at: float | None = None
        self._last_emitted: dict[str, float] = {}

    # -- public API ----------------------------------------------------

    def state(self, now: float) -> StableState | None:
        """Current stable state (None when nothing stable or all expired)."""
        if self._value is None or self._last_observed_at is None:
            return None
        if self._expired(now):
            return None
        return StableState(
            kind=self.kind,
            value=self._value,
            confidence=self._last_confidence or 0.0,
            observed_at=self._last_observed_at,
            confirmed_at=self._stable_since if self._stable_since is not None else self._last_observed_at,
            expires_at=(
                self._last_observed_at + self.ttl_s
                if self.ttl_s is not None
                else None
            ),
            track_id=self.track_id,
        )

    def observe(self, raw: RawObservation | None, *, now: float) -> EvidenceUpdate:
        """One tick: process the observation (or absence) then sweep time."""
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        rejected: list[RejectedObservation] = []
        pending: PendingConfirmation | None = None
        accepted_events: list[StableEvent] = []

        if raw is not None:
            if raw.kind != self.kind or raw.track_id != self.track_id:
                raise ValueError("observation key does not match filter")
            if raw.confidence < self.min_confidence:
                rejected.append(
                    RejectedObservation(raw, RejectionReason.BELOW_CONFIDENCE)
                )
            else:
                pending, accepted_events = self._accept(raw, now, rejected)

        events = tuple(accepted_events + self._sweep(now))
        return EvidenceUpdate(
            state=self.state(now),
            events=events,
            rejected=tuple(rejected),
            pending=pending,
        )

    # -- internals -----------------------------------------------------

    def _accept(
        self, raw: RawObservation, now: float, rejected: list[RejectedObservation]
    ) -> tuple[PendingConfirmation | None, list[StableEvent]]:
        value = raw.value
        if self._value is not None:
            if value == self._value:
                self._refresh(raw, now)
                return None, []
            # competing value: switching requires confirmation (hysteresis)
            if (
                self.hysteresis_conf > 0
                and raw.confidence
                < (self._last_confidence or 0.0) + self.hysteresis_conf
            ):
                rejected.append(RejectedObservation(raw, RejectionReason.SWITCH_PENDING))
                return self._pending_view(now), []
            self._count_candidate(value, raw.confidence, now)
            if self._confirmed():
                return None, self._switch(value, now)
            return self._pending_view(now), []

        # no stable value yet: acquisition path
        self._count_candidate(value, raw.confidence, now)
        if self._confirmed():
            return None, self._promote(value, now)
        return self._pending_view(now), []

    def _refresh(self, raw: RawObservation, now: float) -> None:
        self._last_observed_at = now
        self._last_confidence = raw.confidence
        self._candidate_value = None
        self._candidate_count = 0
        self._candidate_first_at = None
        self._candidate_last_at = None

    def _count_candidate(self, value: str, confidence: float, now: float) -> None:
        if self._candidate_value != value:
            self._candidate_value = value
            self._candidate_count = 1
            self._candidate_first_at = now
        else:
            self._candidate_count += 1
        self._candidate_last_at = now
        self._last_confidence = confidence
        candidate_first_at = self._candidate_first_at
        if candidate_first_at is None:
            candidate_first_at = now
        if (
            self.confirm_window_s is not None
            and now - candidate_first_at > self.confirm_window_s
        ):
            # confirmation window lapsed: restart from this observation
            self._candidate_count = 1
            self._candidate_first_at = now

    def _confirmed(self) -> bool:
        return self._candidate_count >= self.confirm_samples

    def _promote(self, value: str, now: float) -> list[StableEvent]:
        self._value = value
        self._stable_since = now
        self._last_observed_at = now
        self._clear_candidate()
        return self._emit_event(
            _event_name(self.kind, value, released=False),
            now,
            value=value,
            confidence=self._last_confidence or 0.0,
        )

    def _switch(self, value: str, now: float) -> list[StableEvent]:
        old = self._value
        assert old is not None and old != value
        events = self._emit_event(
            _event_name(self.kind, old, released=True),
            now,
            value=old,
            confidence=self._last_confidence or 0.0,
        )
        self._value = value
        self._stable_since = now
        self._last_observed_at = now
        self._clear_candidate()
        events += self._emit_event(
            _event_name(self.kind, value, released=False),
            now,
            value=value,
            confidence=self._last_confidence or 0.0,
        )
        return events

    def _clear_candidate(self) -> None:
        self._candidate_value = None
        self._candidate_count = 0
        self._candidate_first_at = None
        self._candidate_last_at = None

    def _sweep(self, now: float) -> list[StableEvent]:
        """Release a stable value that stopped being observed (edge event)."""
        if self._value is None or self._last_observed_at is None:
            return []
        if not self._expired(now):
            return []
        value = self._value
        confidence = self._last_confidence or 0.0
        self._value = None
        self._last_confidence = None
        self._last_observed_at = None
        self._stable_since = None
        self._clear_candidate()
        return self._emit_event(
            _event_name(self.kind, value, released=True),
            now,
            value=value,
            confidence=confidence,
        )

    def _expired(self, now: float) -> bool:
        assert self._last_observed_at is not None
        age = now - self._last_observed_at
        if self.release_window_s is not None and age >= self.release_window_s:
            return True
        return bool(self.ttl_s is not None and age >= self.ttl_s)

    def _emit_event(
        self, event_name: str, now: float, *, value: str, confidence: float
    ) -> list[StableEvent]:
        """Return the event unless the cooldown suppresses the duplicate."""
        previous = self._last_emitted.get(event_name)
        if previous is not None and now - previous < self.cooldown_s:
            return []
        self._last_emitted[event_name] = now
        return [
            StableEvent(
                self.kind, value, event_name, now, confidence, self.track_id
            )
        ]

    def _pending_view(self, now: float) -> PendingConfirmation | None:
        if self._candidate_value is None:
            return None
        return PendingConfirmation(
            kind=self.kind,
            track_id=self.track_id,
            value=self._candidate_value,
            confirm_count=self._candidate_count,
            confirm_samples=self.confirm_samples,
            observed_at=self._candidate_last_at if self._candidate_last_at is not None else now,
        )


class EvidenceHub:
    """Routes observations from every source into per-key filters.

    One `EvidenceFilter` per (kind, track_id) key. Feeding a tick with
    the tick's `RawObservation`s updates the matching keys and sweeps
    time for every tracked key (absence advances release/TTL). The hub is
    the single entry point through which raw perception reaches stable
    knowledge.
    """

    def __init__(
        self,
        *,
        kind_overrides: Mapping[str, EvidenceFilterParams] | None = None,
        **filter_kwargs: Unpack[EvidenceFilterParams],
    ) -> None:
        self._filters: dict[tuple[str, str | None], EvidenceFilter] = {}
        self._filter_kwargs: EvidenceFilterParams = filter_kwargs
        self._kind_overrides: Mapping[str, EvidenceFilterParams] = (
            kind_overrides or {}
        )
        self._now: float = 0.0

    def _make_filter(self, kind: str, track_id: str | None) -> EvidenceFilter:
        """A filter for one (kind, track_id) key with the hub's policy.

        Global defaults apply to every kind; `kind_overrides` (e.g. a
        gesture-specific confirmation window) layer on top for that kind
        only, so face/person acquisition semantics never change with a
        gesture tuning.
        """
        params: EvidenceFilterParams = {
            **self._filter_kwargs,
            **self._kind_overrides.get(kind, {}),
        }
        return EvidenceFilter(kind, track_id, **params)

    def observe(
        self, raws: list[RawObservation] | tuple[RawObservation, ...], *, now: float
    ) -> EvidenceSnapshot:
        """Feed one tick's raw observations and sweep all tracked keys."""
        if not math.isfinite(now):
            raise ValueError("now must be finite")
        self._now = now
        # index observations by key, keeping the highest-confidence one
        by_key: dict[tuple[str, str | None], RawObservation] = {}
        for raw in raws:
            current = by_key.get(raw.key)
            if current is None or raw.confidence > current.confidence:
                by_key[raw.key] = raw

        states: list[StableState] = []
        events: list[StableEvent] = []
        rejected: list[RejectedObservation] = []
        pending: list[PendingConfirmation] = []
        for key, filt in self._filters.items():
            tick_observation = by_key.get(key)
            update = filt.observe(tick_observation, now=now)
            if update.state is not None:
                states.append(update.state)
            events.extend(update.events)
            rejected.extend(update.rejected)
            if update.pending is not None:
                pending.append(update.pending)
        # create filters for keys seen this tick that are not tracked yet
        for key, entry in by_key.items():
            if key not in self._filters:
                kind, track_id = key
                filt = self._make_filter(kind, track_id)
                self._filters[key] = filt
                update = filt.observe(entry, now=now)
                if update.state is not None:
                    states.append(update.state)
                events.extend(update.events)
                rejected.extend(update.rejected)
                if update.pending is not None:
                    pending.append(update.pending)
        return EvidenceSnapshot(
            states=tuple(states),
            events=tuple(events),
            rejected=tuple(rejected),
            pending=tuple(pending),
        )

    def refresh(self, now: float) -> EvidenceSnapshot:
        """Advance time without new evidence (expiry/release only)."""
        return self.observe([], now=now)

    def state_for(self, kind: str, track_id: str | None = None) -> StableState | None:
        """Latest stable state for a key, staleness vs the last tick time."""
        filt = self._filters.get((kind, track_id))
        return filt.state(self._now) if filt is not None else None

    def reset(self) -> None:
        """Drop all filters: perception restarts from scratch."""
        self._filters.clear()
        self._now = 0.0