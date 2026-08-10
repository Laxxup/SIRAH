"""Stage 8 E2E offline (ADR-0010): the real pipeline over test doubles.

fake camera -> (detector fake) -> GazeBehavior -> SetpointGate ->
TARGET wire -> FakeESP32 twin, plus the degradation rules:

- camera failure DEGRADES camera, runtime continues (heartbeat alive);
- detector failure DEGRADES behavior, runtime continues;
- mid-session link loss DEGRADES eyes (Stage 8 live degradation) and the
  app keeps running with send_errors counted;
- lost_face_center_s recenters the gaze after the face disappears.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sirah.behavior.gaze_behavior import GazeBehavior
from sirah.config.loader import RuntimeSettings
from sirah.config.schema import load_actuator_config
from sirah.hardware.fake_esp32 import FakeESP32
from sirah.hardware.transport import ReadTimeout, TransportError
from sirah.perception.contracts import Frame, GazeTarget
from sirah.perception.replay import JsonlReplayCameraSource
from sirah.runtime.app import RuntimeApp
from sirah.runtime.registry import ComponentStatus

TICK_S = 0.005


class ScriptedCamera:
    """CameraSource double: yields a fixed number of frames, then None."""

    def __init__(self, n: int) -> None:
        self._n = n
        self._sent = 0

    async def start(self) -> None:
        return None

    async def next_frame(self) -> Frame | None:
        if self._sent >= self._n:
            return None
        frame = Frame(index=self._sent)
        self._sent += 1
        return frame

    async def stop(self) -> None:
        return None


class WindowDetector:
    """FaceDetector double: a target for frame indexes in [0, n_faces)."""

    def __init__(self, target: GazeTarget, n_faces: int) -> None:
        self._target = target
        self._n_faces = n_faces

    def detect(self, frame: Frame) -> GazeTarget | None:
        return self._target if frame.index < self._n_faces else None


class ReplayFixtureDetector:
    def detect(self, frame: Frame) -> GazeTarget | None:
        assert isinstance(frame.payload, dict)
        return GazeTarget(0.25, -0.25) if frame.payload["label"] == "empty" else None


class FailAfterCamera(ScriptedCamera):
    """Camera double that dies mid-stream."""

    def __init__(self, n: int, exc: Exception) -> None:
        super().__init__(n)
        self._exc = exc

    async def next_frame(self) -> Frame | None:
        if self._sent >= self._n:
            raise self._exc
        return await super().next_frame()


class FailingDetector:
    """FaceDetector double that always raises."""

    def detect(self, frame: Frame) -> GazeTarget | None:
        raise RuntimeError("detector crashed")


class BurstTransport(FakeESP32):
    """FakeESP32 whose link breaks mid-session on demand."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.break_link = False

    async def send(self, payload: bytes) -> None:
        if self.break_link:
            raise TransportError("link lost mid-session")
        await super().send(payload)


def _settings(*, lost_face_center_s: float = 2.0) -> RuntimeSettings:
    return RuntimeSettings(
        serial_device="/dev/sirah-eyes",
        eyes_armed=True,
        tick_s=TICK_S,
        lost_face_center_s=lost_face_center_s,
        heartbeat_cadence_s=1.0,
    )


def _app(transport: FakeESP32, camera: object, detector: object, behavior: object) -> RuntimeApp:
    return RuntimeApp(
        _settings(),
        load_actuator_config(),
        transport,
        camera=camera,  # type: ignore[arg-type]
        face_detector=detector,  # type: ignore[arg-type]
        behavior=behavior,  # type: ignore[arg-type]
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
    """Ask STATUS and drain queued replies until STATE arrives."""
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


async def test_full_pipeline_sends_target_and_state_converges():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(
        fake,
        ScriptedCamera(n=60),
        WindowDetector(GazeTarget(0.5, -0.5, confidence=0.9), n_faces=60),
        GazeBehavior(),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen == 60)
    await _await_state(fake, lambda x, y: 0.4 < x <= 0.51 and -0.51 <= y < -0.35)
    snapshot = app.registry.snapshot()
    assert snapshot["camera"].status == ComponentStatus.READY
    assert snapshot["behavior"].status == ComponentStatus.READY
    assert snapshot["eyes"].status == ComponentStatus.READY
    stop.set()
    result = await run
    assert result.faces_seen == 60
    x, y = await _read_state(fake)
    assert 0.4 < x <= 0.51
    assert -0.51 <= y < -0.35


async def test_jsonl_replay_fixture_drives_pipeline():
    manifest = Path(__file__).parents[1] / "replay" / "fixtures" / "frames.jsonl"
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake, JsonlReplayCameraSource(manifest), ReplayFixtureDetector(), GazeBehavior())
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen == 1)
    await _await_state(fake, lambda x, y: x > 0.1 and y < -0.05)
    stop.set()
    result = await run
    assert result.send_errors == 0


async def test_lost_face_recenters_to_center_after_timeout():
    fake = FakeESP32.from_actuators_yaml()
    app = RuntimeApp(
        _settings(lost_face_center_s=0.06),
        load_actuator_config(),
        fake,
        camera=ScriptedCamera(n=10**6),  # type: ignore[arg-type]
        face_detector=WindowDetector(GazeTarget(0.5, -0.5, confidence=0.9), n_faces=30),  # type: ignore[arg-type]
        behavior=GazeBehavior(),  # type: ignore[arg-type]
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen == 30)
    await _await_state(fake, lambda x, y: abs(x) < 0.05 and abs(y) < 0.05)
    stop.set()
    result = await run
    assert result.faces_seen == 30
    assert result.send_errors == 0


async def test_camera_failure_degrades_but_runtime_continues():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(
        fake,
        FailAfterCamera(n=5, exc=OSError("camera unplugged")),
        WindowDetector(GazeTarget(0.5, -0.5, confidence=0.9), n_faces=10**9),
        GazeBehavior(),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.registry.get("camera").status == ComponentStatus.DEGRADED)
    await asyncio.sleep(0.1)
    assert app.registry.get("eyes").status == ComponentStatus.READY  # heartbeat survives
    stop.set()
    await run  # no exception: runtime survives a dead camera


async def test_detector_failure_degrades_behavior_but_runtime_continues():
    fake = FakeESP32.from_actuators_yaml()
    app = _app(fake, ScriptedCamera(n=60), FailingDetector(), GazeBehavior())
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.registry.get("behavior").status == ComponentStatus.DEGRADED)
    assert app.registry.get("camera").status == ComponentStatus.READY
    assert app.registry.get("eyes").status == ComponentStatus.READY
    stop.set()
    await run


async def test_mid_session_link_loss_degrades_eyes_and_counts():
    fake = BurstTransport.from_actuators_yaml()
    app = _app(
        fake,
        ScriptedCamera(n=10**6),
        WindowDetector(GazeTarget(0.5, -0.5, confidence=0.9), n_faces=10**9),
        GazeBehavior(),
    )
    stop = asyncio.Event()
    run = asyncio.create_task(app.run(stop))
    await _await_until(lambda: app.result.faces_seen > 0)
    fake.break_link = True
    await _await_until(lambda: app.registry.get("eyes").status == ComponentStatus.DEGRADED)
    await asyncio.sleep(0.1)
    assert app.result.send_errors == 1  # counted once, no retry storm
    stop.set()
    result = await run
    assert result.send_errors == 1
    assert result.registry.get("eyes").status == ComponentStatus.DEGRADED
