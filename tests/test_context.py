"""Pruebas del contexto presente en memoria."""

from sirah.context import ConversationMessage, SessionContextStore


def test_context_keeps_recent_messages() -> None:
    store = SessionContextStore(max_messages=2)
    for text in ("uno", "dos", "tres"):
        store.append("session", ConversationMessage("user", text))
    assert [message.text for message in store.get("session").messages] == [
        "dos",
        "tres",
    ]


def test_context_discards_old_messages_by_character_budget() -> None:
    store = SessionContextStore(max_characters=5)
    store.append("session", ConversationMessage("user", "abc"))
    store.append("session", ConversationMessage("assistant", "def"))
    assert [message.text for message in store.get("session").messages] == ["def"]


def test_sessions_do_not_mix() -> None:
    store = SessionContextStore()
    store.append("a", ConversationMessage("user", "solo a"))
    assert store.get("b").messages == ()


def test_last_action_is_updated() -> None:
    store = SessionContextStore()
    context = store.update_action(
        "session", capability="robot.home", result="succeeded"
    )
    assert context.last_requested_capability == "robot.home"
    assert context.last_capability_result == "succeeded"


def test_context_does_not_persist_between_instances() -> None:
    first = SessionContextStore()
    first.append("session", ConversationMessage("user", "temporal"))
    assert SessionContextStore().get("session").messages == ()


def test_safety_state_is_explicit() -> None:
    store = SessionContextStore()
    assert store.set_safety_state("session", "emergency").safety_state == "emergency"

