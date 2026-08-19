"""M8.1: perception -> compact AI vision context (unit, no camera/model).

Checks the pure feed helpers (`face_observation`, `person_observations`)
and the formatter/provider that turn stable evidence into the few compact
Spanish lines the conversation AI can ground answers on. Everything here
is deterministic and hardware-free.
"""

from __future__ import annotations

from sirah.perception.contracts import GazeTarget
from sirah.perception.evidence import EvidenceHub, RawObservation, StableEvent
from sirah.perception.person import ObservedScene, PersonTrack, TrackLifecycle
from sirah.perception.vision_context import (
    DEFAULT_RECENT_LIMIT,
    VisionContextProvider,
    face_observation,
    person_observations,
)
from sirah.perception.world_state import PerceptionFacts


def _track(
    track_id: int, lifecycle: TrackLifecycle, *, velocity=None, confidence: float = 0.9
) -> PersonTrack:
    return PersonTrack(
        track_id,
        lifecycle,
        0.1,
        0.1,
        0.3,
        0.5,
        confidence,
        first_seen=0.0,
        last_seen=1.0,
        last_source_frame_index=5,
        velocity=velocity,
    )


def _scene(*tracks: PersonTrack) -> ObservedScene:
    return ObservedScene(
        tracks=tuple(tracks), observed_at=0.0, source_frame_index=5
    )


def _facts(
    raws: list[RawObservation], *, now: float = 0.0
) -> tuple[PerceptionFacts, tuple[StableEvent, ...]]:
    hub = EvidenceHub(confirm_samples=1)
    snapshot = hub.observe(tuple(raws), now=now)
    return (
        PerceptionFacts.from_snapshot(snapshot, observed_at=now),
        snapshot.events,
    )


def _provider(facts: PerceptionFacts, events: tuple[StableEvent, ...], *, now: float) -> VisionContextProvider:
    provider = VisionContextProvider(clock=lambda: 0.0)
    provider.observe(facts, events, now=now)
    return provider


def _text(provider: VisionContextProvider, *, now: float) -> str | None:
    return provider.snapshot(now=now).text


# -- feed helpers ------------------------------------------------------


def test_face_observation_uses_face_kind_and_primary_track():
    obs = face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)
    assert obs.kind == "face"
    assert obs.track_id == "primary"
    assert obs.value == "present"
    assert obs.confidence == 0.9
    assert obs.source == "yunet"


def test_face_observation_without_target_yields_zero_confidence():
    obs = face_observation(None, now=0.0)
    assert obs.kind == "face"
    assert obs.confidence == 0.0


def test_person_observations_only_active_tracks_with_motion():
    scene = _scene(
        _track(0, TrackLifecycle.CONFIRMED, velocity=(0.01, 0.01)),
        _track(3, TrackLifecycle.CONFIRMED, velocity=(0.4, 0.05)),
        _track(1, TrackLifecycle.TEMPORARILY_LOST),
    )
    kinds = {(o.kind, o.value, o.track_id) for o in person_observations(scene, now=0.0)}
    assert ("person", "present", "track_0") in kinds
    assert ("motion", "stationary", "track_0") in kinds
    assert ("person", "present", "track_3") in kinds
    assert ("motion", "moving", "track_3") in kinds
    assert not any(track_id == "track_1" for _, _, track_id in kinds)


def test_person_observations_without_velocity_omit_motion():
    scene = _scene(_track(0, TrackLifecycle.CONFIRMED, velocity=None))
    obs = person_observations(scene, now=0.0)
    assert len(obs) == 1
    assert obs[0].kind == "person"


def test_person_observations_empty_scene_yields_nothing():
    assert person_observations(None, now=0.0) == ()
    assert person_observations(_scene(), now=0.0) == ()


# -- formatter / provider ---------------------------------------------


def test_current_person_face_and_motion_state_formatted():
    raws = [face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)]
    raws.extend(
        person_observations(
            _scene(
                _track(0, TrackLifecycle.CONFIRMED, velocity=(0.01, 0.01)),
                _track(3, TrackLifecycle.CONFIRMED, velocity=(0.4, 0.05)),
            ),
            now=0.0,
        )
    )
    facts, events = _facts(raws, now=0.0)
    text = _text(_provider(facts, events, now=0.0), now=0.5)
    assert text is not None
    assert text.startswith("VISIÓN ACTUAL:")
    assert "Personas visibles: #0, #3." in text
    assert "Persona #0 está quieta." in text
    assert "Persona #3 está en movimiento." in text
    assert "Un rostro está visible." in text


def test_expired_states_drop_from_current_section():
    raws = [face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)]
    raws.extend(person_observations(_scene(_track(3, TrackLifecycle.CONFIRMED)), now=0.0))
    facts, events = _facts(raws, now=0.0)  # default TTL is 3.0s
    text = _text(_provider(facts, events, now=0.0), now=3.5)
    assert text is not None
    assert "No hay personas visibles." in text
    assert "Persona visible" not in text
    assert "Un rostro está visible." not in text


def test_gesture_state_appears_when_fresh_and_drops_when_stale():
    raws = [RawObservation("gesture", "gesture", "thumb_up", 0.9, 0.0, "Right")]
    facts, events = _facts(raws, now=0.0)
    provider = _provider(facts, events, now=0.0)
    assert "Gesto: thumb_up." in _text(provider, now=0.5)
    assert "Gesto:" not in _text(provider, now=3.5)


def test_recent_events_reported_once_with_age_and_no_motion_noise():
    raws = [face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)]
    raws.extend(person_observations(_scene(_track(0, TrackLifecycle.CONFIRMED)), now=0.0))
    facts, events = _facts(raws, now=0.0)
    text = _text(_provider(facts, events, now=0.0), now=2.0)
    assert text is not None
    assert text.count("Persona #0 entró hace 2.0s.") == 1
    assert text.count("Un rostro apareció hace 2.0s.") == 1
    assert "motion" not in text  # motion is current state, never event news


def test_vision_unavailable_returns_none():
    provider = VisionContextProvider(clock=lambda: 0.0)
    assert provider.text() is None


def test_vision_lapses_after_availability_window():
    facts, events = _facts([face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)], now=0.0)
    provider = _provider(facts, events, now=0.0)
    assert _text(provider, now=5.5) is None


def test_empty_perception_is_available_but_explicitly_unknown():
    facts, events = _facts([], now=0.0)
    text = _text(_provider(facts, events, now=0.0), now=0.5)
    assert text is not None
    assert "Sin información visual fresca." in text
    assert "No hay personas visibles." not in text  # no absence claim from no data


def test_multiple_tracks_reported_separately_not_fused():
    raws = list(
        person_observations(
            _scene(
                _track(0, TrackLifecycle.CONFIRMED),
                _track(3, TrackLifecycle.CONFIRMED),
            ),
            now=0.0,
        )
    )
    facts, events = _facts(raws, now=0.0)
    text = _text(_provider(facts, events, now=0.0), now=0.5)
    assert text is not None
    assert "#0" in text and "#3" in text
    assert "Personas visibles: #0, #3." in text


def test_context_never_exposes_raw_diagnostics():
    raws = [face_observation(GazeTarget(0.2, -0.3, 0.9), now=0.0)]
    raws.extend(
        person_observations(
            _scene(
                _track(0, TrackLifecycle.CONFIRMED, velocity=(0.01, 0.01)),
                _track(3, TrackLifecycle.CONFIRMED, velocity=(0.4, 0.05)),
            ),
            now=0.0,
        )
    )
    raws.append(RawObservation("gesture", "gesture", "victory", 0.9, 0.0, "Right"))
    facts, events = _facts(raws, now=0.0)
    text = _text(_provider(facts, events, now=0.0), now=0.5)
    assert text is not None
    for forbidden in (
        "yunet",
        "person_tracker",
        "mediapipe",
        "efficientdet",
        "landmark",
        "confidence",
        "conf=",
        "0.2",
        "-0.3",
        "numpy",
        "bbox",
        "primary",
    ):
        assert forbidden not in text
    assert text.startswith("VISIÓN ACTUAL:")


def test_recent_section_is_bounded():
    provider = VisionContextProvider(clock=lambda: 0.0)
    facts, _ = _facts([], now=0.0)
    events = tuple(
        StableEvent(
            kind="person",
            value="present",
            event=f"evt{index}",
            observed_at=0.0,
            confidence=0.9,
            track_id="track_0",
        )
        for index in range(100)
    )
    provider.observe(facts, events, now=0.0)
    context = provider.snapshot(now=0.5)
    assert len(context.recent) <= DEFAULT_RECENT_LIMIT