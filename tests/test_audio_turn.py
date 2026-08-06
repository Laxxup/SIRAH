"""Test AudioTurnCoordinator."""

from __future__ import annotations

import asyncio

import pytest

from sirah.errors import AudioTurnBusyError
from sirah.voice.coordinator import (
    AudioTurnCoordinator,
    AudioTurnDirection,
)


@pytest.mark.asyncio
async def test_coordinator_reserve_release() -> None:
    coord = AudioTurnCoordinator()
    lease_id = await coord.reserve(AudioTurnDirection.OUTPUT)
    assert coord.direction == AudioTurnDirection.OUTPUT
    await coord.release(lease_id)
    assert coord.is_free


@pytest.mark.asyncio
async def test_coordinator_double_reserve_fails() -> None:
    coord = AudioTurnCoordinator()
    await coord.reserve(AudioTurnDirection.OUTPUT)
    with pytest.raises(AudioTurnBusyError):
        await coord.reserve(AudioTurnDirection.INPUT)


@pytest.mark.asyncio
async def test_coordinator_wrong_lease_id_noop() -> None:
    coord = AudioTurnCoordinator()
    lid = await coord.reserve(AudioTurnDirection.OUTPUT)
    await coord.release("wrong-id")
    assert not coord.is_free
    await coord.release(lid)
    assert coord.is_free


@pytest.mark.asyncio
async def test_coordinator_release_twice_noop() -> None:
    coord = AudioTurnCoordinator()
    lid = await coord.reserve(AudioTurnDirection.OUTPUT)
    await coord.release(lid)
    await coord.release(lid)
    assert coord.is_free


@pytest.mark.asyncio
async def test_coordinator_sequential_turns() -> None:
    coord = AudioTurnCoordinator()
    lid1 = await coord.reserve(AudioTurnDirection.OUTPUT)
    await coord.release(lid1)
    lid2 = await coord.reserve(AudioTurnDirection.INPUT)
    assert coord.direction == AudioTurnDirection.INPUT
    await coord.release(lid2)
    assert coord.is_free


@pytest.mark.asyncio
async def test_coordinator_concurrency() -> None:
    coord = AudioTurnCoordinator()
    results: list[str] = []

    async def try_reserve(name: str) -> None:
        while True:
            try:
                lid = await coord.reserve(AudioTurnDirection.OUTPUT)
                results.append(f"{name}_got")
                await asyncio.sleep(0.05)
                await coord.release(lid)
                results.append(f"{name}_released")
                return
            except AudioTurnBusyError:
                results.append(f"{name}_busy")
                await asyncio.sleep(0.01)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(try_reserve("A"))
        tg.create_task(try_reserve("B"))

    assert "A_got" in results
    assert "A_released" in results
    assert "B_got" in results
    assert "B_released" in results
