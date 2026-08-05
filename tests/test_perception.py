"""Test perception layer."""

from __future__ import annotations

import pytest

from sirah.perception.simulated import SimulatedPerception
from sirah.types import FaceDetection, PerceptionFrame
from sirah.errors import PerceptionUnavailableError


@pytest.mark.asyncio
async def test_simulated_perception_no_faces() -> None:
    p = SimulatedPerception()
    await p.start()
    frame = await p.capture()
    assert len(frame.faces) == 0
    await p.stop()


@pytest.mark.asyncio
async def test_simulated_perception_with_faces() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.95)
    p = SimulatedPerception(scripted_faces=[(face,)])
    await p.start()
    frame = await p.capture()
    assert len(frame.faces) == 1
    assert frame.faces[0].confidence == 0.95
    await p.stop()


@pytest.mark.asyncio
async def test_simulated_perception_iterates() -> None:
    f1 = FaceDetection(bbox=(0.0, 0.0, 0.2, 0.2), confidence=0.8)
    f2 = FaceDetection(bbox=(0.5, 0.5, 0.3, 0.3), confidence=0.9)
    p = SimulatedPerception(scripted_faces=[(f1,), (f2,)])
    await p.start()
    r1 = await p.capture()
    r2 = await p.capture()
    r3 = await p.capture()
    assert r1.faces[0].confidence == 0.8
    assert r2.faces[0].confidence == 0.9
    assert r3.faces[0].confidence == 0.9
    await p.stop()


@pytest.mark.asyncio
async def test_simulated_perception_health() -> None:
    p = SimulatedPerception()
    assert await p.health() is False
    await p.start()
    assert await p.health() is True
    await p.stop()
    assert await p.health() is False


@pytest.mark.asyncio
async def test_simulated_perception_failure() -> None:
    p = SimulatedPerception(fail_after=2)
    await p.start()
    await p.capture()
    await p.capture()
    with pytest.raises(PerceptionUnavailableError, match="simulated failure"):
        await p.capture()
    await p.stop()


@pytest.mark.asyncio
async def test_simulated_perception_reset() -> None:
    face = FaceDetection(bbox=(0.1, 0.1, 0.3, 0.3), confidence=0.9)
    p = SimulatedPerception(scripted_faces=[(face,)])
    await p.start()
    await p.capture()
    assert p._index == 1
    p.reset()
    assert p._index == 0
    await p.stop()
