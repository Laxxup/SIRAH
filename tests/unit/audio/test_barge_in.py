from __future__ import annotations

from sirah.audio.barge_in import BargeInController


class Cancellable:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel(self, operation_id: str) -> None:
        self.cancelled.append(operation_id)


async def test_barge_in_invalidates_active_operation_before_cancelling_audio():
    player = Cancellable()
    tts = Cancellable()
    barge_in = BargeInController(player, tts)
    barge_in.activate("reply-1")

    assert await barge_in.interrupt() == "reply-1"
    assert not barge_in.is_active("reply-1")
    assert player.cancelled == ["reply-1"]
    assert tts.cancelled == ["reply-1"]


async def test_barge_in_without_active_operation_does_not_cancel_audio():
    player = Cancellable()
    tts = Cancellable()
    barge_in = BargeInController(player, tts)

    assert await barge_in.interrupt() is None
    assert player.cancelled == []
    assert tts.cancelled == []
