"""Attention + arbitration + world-state integration (M8/M9/M10): the real
runtime pipeline over test doubles.

camera -> MultiFaceDetector -> AttentionManager -> GazeBehavior ->
EyeArbiter -> SetpointGate -> TARGET -> FakeESP32, proving that:

- attention stabilizes the primary target when several faces are present;
- a manual claim overrides face tracking by arbitration priority;
- world state reflects the pipeline without any hardware.

No OpenCV, no model, no serial, no servos: fully offline (ADR-0010).
"""

from __future__ import annotations

import asyncio

from sirah.behavior.attention import AttentionManager
from sirah.behavior.gaze_behavior import GazeBehavior
from sirah.config.loader import RuntimeSettings
from sirah.config.schema import load_actuator_config
from sirah.hardware.fake_esp32 import FakeESP32
from sirah.hardware.transport import ReadTimeout
from sirah.perception.contracts import Frame, GazeTarget
from sirah.runtime.app import RuntimeApp
from sirah.runtime.policies import Setpoint
from sirah.runtime.registry import ComponentStatus

TICK_S = 0.005
FACE = GazeTarget(0.5, -0.2, confidence=0.9)


class ScriptedCamera:
    """CameraSource double: yields frames with capture timestamps forever."""

    def __init__(self, captured_at: float = 0.0) -> None:
        self._sent = 0
        self._captured_at = captured_at

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        self._captured_at += 0.02
        frame = Frame(index=self._sent, captured_at=self._captured_at)
        self._sent += 1
        return frame

    async def stop(self) -> None:
        return None


class AlternatingMultiDetector:
    """Two faces present every frame; each frame they swap confidence."""

    def detect_many(self, frame: Frame):
        if frame.index % 2 == 0:
            return [GazeTarget(0.5, -0.2, 0.95), GazeTarget(-0.5, 0.2, 0.8)]
        return [GazeTarget(0.5, -0.2, 0.8), GazeTarget(-0.5, 0.2, 0.95)]


class WindowedDetector:
    """Single-target detector: a face for frames [0, n_faces), then none."""

    def __init__(self, target: GazeTarget, n_faces: int) -> None:
        self._target = target
        self._n_faces = n_faces

    def detect(self, frame: Frame) -> GazeTarget | None:
        return self._target if frame.index < self._n_faces else None


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        serial_device="/dev/sirah-eyes",
        eyes_armed=True,
        tick_s=TICK_S,
        lost_face_center_s=0.06,
        heartbeat_cadence_s=1.0,
    )


def _app(transport: FakeESP32, **components: object) -> RuntimeApp:
    return RuntimeApp(  # type: ignore[arg-type]
        _settings(),
        load_actuator_config(),
        transport,
        **components,
    )


async def _await_until(predicate: object, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():  # type: ignore[operator]
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"condition not met within {timeout}s")


async def _read_state(fake: FakeESP32) -> tuple[float, float]:
    await fake.send(b"STATUS")
    for _ in range(500):
        try:
            line = await fake.read(timeout=0.05)
        except ReadTimeout:
            continue
        if line is None:
            continue
        if line.startswith(b"STATE"):
            _, xs, ys, _ = line.split()
            return float(xs), float(ys)
    raise AssertionError("no STATE reply received")


async def _await_state(fake: FakeESP32, predicate: object, timeout: float = 3.0) -> tuple[float, float]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        x, y = await _read_state(fake)
        if predicate(x, y):  # type: ignore[operator]
            return x, y
        await asyncio.sleep(0.01)
    raise AssertionError("STATE never matched the predicate")


async def test_attention_stabilizes_primary_with_multiple_faces():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(
        fake,
        camera=ScriptedCamera(),
        face_detector=AlternatingMultiDetector(),
        behavior=GazeBehavior(),
        attention=AttentionManager(acquire_samples=1),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen > 40)
    assert app.registry.get("attention").status == ComponentStatus.READY
    assert app.result.gaze_producer == "face_tracking"
    # Attention keeps the SAME face despite alternating confidence: gaze
    # converges to x≈0.5 (the acquired face), never swinging to x≈-0.5.
    assert app.world_state is not None
    assert app.world_state.face_present
    assert app.world_state.primary_target is not None
    assert app.world_state.primary_target.x == 0.5
    x, y = await _read_state(fake)
    assert x > 0.3 and y < -0.1
    stop.set()
    result = await run
    assert result.send_errors == 0


async def test_manual_claim_overrides_face_tracking():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(
        fake,
        camera=ScriptedCamera(),
        face_detector=WindowedDetector(FACE, n_faces=10**9),
        behavior=GazeBehavior(),
        manual_provider=lambda: Setpoint(0.9, -0.9),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen > 20)
    await _await_until(
        lambda: app.result.gaze_producer == "manual"
        and app.world_state is not None
        and app.world_state.gaze_x == 0.9
    )
    assert app.world_state is not None
    assert app.world_state.gaze_producer == "manual"
    assert app.world_state.gaze_x == 0.9
    assert app.world_state.gaze_y == -0.9
    x, y = await _await_state(fake, lambda px, py: px > 0.4 and py < -0.4)
    assert x > 0.4 and y < -0.4  # the eyes actually followed the manual claim
    stop.set()
    await run


async def test_attention_release_and_world_state_reflect_loss():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(
        fake,
        camera=ScriptedCamera(),
        face_detector=WindowedDetector(FACE, n_faces=8),
        behavior=GazeBehavior(),
        attention=AttentionManager(acquire_samples=1, loss_hold_samples=2),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen == 8)
    await _await_until(lambda: app.world_state is not None and not app.world_state.face_present)
    # With the face gone, attention releases and the lost-face policy
    # recenters the gaze to CENTER (0, 0).
    x, y = await _await_state(fake, lambda px, py: abs(px) < 0.1 and abs(py) < 0.1)
    assert abs(x) < 0.1 and abs(y) < 0.1
    assert app.world_state is not None
    assert app.world_state.face_present is False
    stop.set()
    await run