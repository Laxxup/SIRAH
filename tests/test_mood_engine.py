"""Test MoodEngine."""

from __future__ import annotations

from sirah.autonomy.mood_engine import MoodEngine, MoodState


def test_mood_default_neutral() -> None:
    m = MoodEngine()
    assert m.state == MoodState.NEUTRAL


def test_mood_custom_initial() -> None:
    m = MoodEngine(initial=MoodState.HAPPY)
    assert m.state == MoodState.HAPPY


def test_mood_transition_person_greeted() -> None:
    m = MoodEngine()
    m.update(("person_greeted",))
    assert m.state == MoodState.HAPPY


def test_mood_transition_person_new() -> None:
    m = MoodEngine()
    m.update(("person_new",))
    assert m.state == MoodState.CURIOUS


def test_mood_transition_late_night() -> None:
    m = MoodEngine()
    m.update(("late_night",))
    assert m.state == MoodState.TIRED


def test_mood_transition_user_sad() -> None:
    m = MoodEngine()
    m.update(("user_sad",))
    assert m.state == MoodState.CONCERNED


def test_mood_system_prompt_changes() -> None:
    m = MoodEngine()
    neutral_prompt = m.system_prompt
    m.update(("person_greeted",))
    happy_prompt = m.system_prompt
    assert neutral_prompt != happy_prompt
    assert "buen humor" in happy_prompt.lower() or "cálido" in happy_prompt.lower()


def test_mood_initiative_interval_per_state() -> None:
    m = MoodEngine(initial=MoodState.NEUTRAL)
    assert m.initiative_interval_s == 2.0

    m.update(("person_greeted",))
    assert m.initiative_interval_s == 1.0

    m.update(("late_night",))
    assert m.initiative_interval_s == 5.0

    m.update(("user_sad",))
    assert m.initiative_interval_s == 0.3


def test_mood_speech_speed_per_state() -> None:
    m = MoodEngine(initial=MoodState.TIRED)
    assert m.speech_speed < 1.0

    m.update(("person_greeted",))
    assert m.speech_speed == 1.0


def test_mood_reset() -> None:
    m = MoodEngine()
    m.update(("person_greeted",))
    assert m.state == MoodState.HAPPY
    m.reset()
    assert m.state == MoodState.NEUTRAL
    assert len(m.log) == 0


def test_mood_log_transitions() -> None:
    m = MoodEngine()
    m.update(("person_greeted",))
    m.update(("late_night",))
    assert len(m.log) == 2


def test_mood_all_states_have_prompt() -> None:
    for state in MoodState:
        m = MoodEngine(initial=state)
        assert len(m.system_prompt) > 0


def test_mood_prompts_preserve_multimodal_capabilities() -> None:
    prompt = MoodEngine().system_prompt.lower()

    assert "cámara" in prompt
    assert "micrófono" in prompt
    assert "parlantes" in prompt
    assert "nunca digas" in prompt
    assert "no tienes acceso visual" in prompt
