"""Test ConversationContext."""

from __future__ import annotations

from sirah.core.context import ConversationContext
from sirah.types import ConversationMessage, PresentContext


def test_context_add_message() -> None:
    ctx = ConversationContext(max_messages=8)
    ctx.add(ConversationMessage(role="user", content="hola"))
    assert len(ctx.messages) == 1
    assert ctx.last_user_text == "hola"


def test_context_trim_messages() -> None:
    ctx = ConversationContext(max_messages=3)
    for i in range(5):
        ctx.add(ConversationMessage(role="user", content=f"msg{i}"))
    assert len(ctx.messages) == 3


def test_context_last_user_finds_latest() -> None:
    ctx = ConversationContext()
    ctx.add(ConversationMessage(role="user", content="primero"))
    ctx.add(ConversationMessage(role="assistant", content="respuesta"))
    ctx.add(ConversationMessage(role="user", content="segundo"))
    assert ctx.last_user_text == "segundo"


def test_context_is_empty() -> None:
    ctx = ConversationContext()
    assert ctx.is_empty
    ctx.add(ConversationMessage(role="user", content="x"))
    assert not ctx.is_empty


def test_context_clear() -> None:
    ctx = ConversationContext()
    ctx.add(ConversationMessage(role="user", content="x"))
    ctx.clear()
    assert ctx.is_empty


def test_context_present() -> None:
    ctx = ConversationContext()
    assert ctx.present.user_text is None
    ctx.present = PresentContext(user_text="test", face_count=1)
    assert ctx.present.face_count == 1
