from __future__ import annotations

import asyncio

import pytest

from sirah.audio.playback import PCMPlayer


async def test_player_delivers_pcm_to_injected_sink():
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        delivered.append(pcm)

    player = PCMPlayer(sink)
    await player.play("reply-1", b"pcm")
    await player.join()

    assert delivered == [b"pcm"]
    await player.close()


async def test_cancelling_an_operation_stops_active_and_drops_queued_pcm():
    started = asyncio.Event()
    released = asyncio.Event()
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        started.set()
        await released.wait()
        delivered.append(pcm)

    player = PCMPlayer(sink, queue_size=2)
    await player.play("reply-1", b"active")
    await started.wait()
    await player.play("reply-1", b"queued")

    await player.cancel("reply-1")
    released.set()
    await player.join()

    assert delivered == []
    await player.close()


async def test_player_keeps_queue_bounded_while_waiting_for_sink():
    started = asyncio.Event()
    released = asyncio.Event()
    delivered: list[bytes] = []

    async def sink(pcm: bytes) -> None:
        started.set()
        await released.wait()
        delivered.append(pcm)

    player = PCMPlayer(sink, queue_size=1)
    await player.play("reply-1", b"active")
    await started.wait()
    await player.play("reply-2", b"queued")
    blocked = asyncio.create_task(player.play("reply-3", b"blocked"))
    await asyncio.sleep(0)

    assert not blocked.done()

    await player.cancel("reply-3")
    with pytest.raises(asyncio.CancelledError):
        await blocked
    released.set()
    await player.join()
    assert delivered == [b"active", b"queued"]
    await player.close()
