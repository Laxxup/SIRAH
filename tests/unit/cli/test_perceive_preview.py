"""sirah-perceive preview tests (M4): the diagnostic evidence path over
fakes needs no OpenCV, model, camera or hardware."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from sirah.behavior.attention import AttentionManager
from sirah.cli.perceive import perceive_preview
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.evidence import EvidenceHub, RejectionReason


class FakeCamera:
    def __init__(self, frames: list[object]) -> None:
        self._frames = iter(frames)
        self.stopped = False

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        try:
            payload = next(self._frames)
        except StopIteration:
            return None
        return Frame(index=payload[0], payload=None, captured_at=payload[1])

    async def stop(self) -> None:
        self.stopped = True


class MultiFaceDetector:
    def __init__(self, targets: dict[int, list[GazeTarget]]) -> None:
        self._targets = targets

    def detect_many(self, frame: Frame) -> list[GazeTarget]:
        return self._targets.get(frame.index, [])


def _advancing_clock() -> Callable[[], float]:
    state = {"t": -0.1}

    def clock() -> float:
        state["t"] += 0.1
        return state["t"]

    return clock


async def test_preview_confirms_person_after_two_frames():
    camera = FakeCamera([(0, 0.0), (1, 0.1), (2, 0.2), (3, 0.3)])
    detector = MultiFaceDetector(
        {
            0: [GazeTarget(0.2, -0.3, 0.9)],
            1: [GazeTarget(0.2, -0.3, 0.91)],
            2: [],
            3: [],
        }
    )
    summary = await perceive_preview(
        camera,
        detector,
        max_frames=4,
        clock=_advancing_clock(),
        evidence=EvidenceHub(release_window_s=0.05),
        attention=_minimal_attention(),
    )
    assert summary.frames == 4
    assert summary.faces == 2
    # face confirmed after 2 samples → exactly one confirm event
    assert summary.all_events.count("face_present_confirmed") == 1
    # face disappears after the release grace → released once
    assert summary.all_events.count("face_present_released") == 1
    assert camera.stopped


async def test_preview_reports_rejected_absence_as_diagnostic():
    camera = FakeCamera([(0, 0.0)])
    detector = MultiFaceDetector({0: []})
    summary = await perceive_preview(camera, detector, max_frames=1, clock=lambda: 0.0)
    assert summary.rejected_count == 1
    rejected = summary.observations[0].rejected
    assert rejected and rejected[0].reason == RejectionReason.BELOW_CONFIDENCE


async def test_preview_reports_pending_confirmation():
    camera = FakeCamera([(0, 0.0)])
    detector = MultiFaceDetector({0: [GazeTarget(0.2, -0.3, 0.9)]})
    summary = await perceive_preview(
        camera,
        detector,
        max_frames=1,
        clock=lambda: 0.0,
        attention=_minimal_attention(),
    )
    pending = summary.observations[0].pending
    assert pending
    assert pending[0].value == "present"
    assert pending[0].confirm_count == 1
    assert pending[0].confirm_samples == 2


async def test_preview_records_detector_latency_and_frame_age():
    camera = FakeCamera([(0, 10.0), (1, 10.1)])
    detector = MultiFaceDetector(
        {0: [GazeTarget(0.0, 0.0, 0.9)], 1: [GazeTarget(0.0, 0.0, 0.9)]}
    )
    summary = await perceive_preview(camera, detector, max_frames=2, clock=lambda: 10.25)
    assert summary.detect_p50 is not None and summary.detect_p50 >= 0
    assert summary.detect_p95 is not None
    assert summary.frame_age_p50 == pytest.approx(0.2)
    assert summary.frame_age_p95 == pytest.approx(0.25)


async def test_preview_stops_camera_on_cancellation():
    camera = FakeCamera([(0, 0.0), (1, 0.1)])
    detector = MultiFaceDetector({})
    task = asyncio.create_task(
        perceive_preview(camera, detector, max_frames=0, clock=lambda: 0.0)
    )
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert camera.stopped


async def test_preview_accepts_injected_evidence_hub():
    hub = EvidenceHub(confirm_samples=1)
    camera = FakeCamera([(0, 0.0)])
    detector = MultiFaceDetector({0: [GazeTarget(0.2, -0.3, 0.9)]})
    summary = await perceive_preview(
        camera,
        detector,
        max_frames=1,
        clock=lambda: 0.0,
        attention=_minimal_attention(),
        evidence=hub,
    )
    assert hub.state_for("face", "primary") is not None
    assert "face_present_confirmed" in summary.all_events

def _minimal_attention() -> AttentionManager:
    return AttentionManager(acquire_samples=1, loss_hold_samples=1, switch_samples=1)
