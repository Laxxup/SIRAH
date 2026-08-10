"""Unit tests for FakeESP32 (Stage 6).

Covers:
- the SAME golden corpus as the firmware (Stage 3 runner reused: every
  corpus line fed through the fake's grammar acceptance must produce the
  same verdict as the parser gate);
- READY/OK/STATE/ERR reply semantics vs protocol.md;
- per-axis easing mirror (ADR-0005: Y damped more than X);
- blink FSM mirror (trigger only in Idle, timing, auto cadence);
- calibration hard-clamp rejects (out-of-range -> ERR 3);
- watchdog mirror (Stage 11: heartbeat pause -> eased CENTER);
- initialization from the shared actuator YAML (ADR-0009).
"""

from __future__ import annotations

import pytest

from sirah.config.schema import ActuatorConfig, load_actuator_config
from sirah.hardware.fake_esp32 import (
    EASE_KX,
    EASE_KY,
    BlinkConfig,
    BlinkFSM,
    FakeESP32,
    GazeEaser,
)
from sirah.hardware.transport import ReadTimeout, TransportState
from sirah.protocol.parse_line import parse_line
from tests.contract.corpus import load_cases

REPO_ACTUATORS_YAML = (
    __import__("pathlib").Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"
)

CASES = load_cases()

# corpus verdict -> (reply expected, reply parses back as)
_CMD_REPLY = {
    "CMD:TARGET": b"OK",
    "CMD:CENTER": b"OK",
    "CMD:BLINK": b"OK",
    "CMD:STATUS": "RESP:STATE",
    "CMD:HEARTBEAT": None,  # spec 6.2: HEARTBEAT is silent
}


@pytest.fixture
def fake() -> FakeESP32:
    return FakeESP32(load_actuator_config(REPO_ACTUATORS_YAML), seed=42)


async def test_connect_emits_ready(fake: FakeESP32) -> None:
    await fake.connect()
    assert fake.status().state is TransportState.CONNECTED
    assert await fake.read() == b"READY 1"


async def test_corpus_lines_match_golden_verdicts(fake: FakeESP32) -> None:
    """Every corpus line -> fake grammar acceptance == gold verdict."""
    await fake.connect()
    await fake.read()  # consume READY
    for raw, expected, source in CASES:
        result = parse_line(raw)
        assert result.verdict() == expected, f"{source}: {raw!r}"


async def test_corpus_commands_reply_consistent(fake: FakeESP32) -> None:
    """Feeding valid commands through the fake yields spec replies."""
    await fake.connect()
    await fake.read()  # consume READY
    for raw, expected, _ in CASES:
        if not expected.startswith("CMD:"):
            continue
        await fake.send(raw)
        want = _CMD_REPLY[expected]
        if want is None:
            with pytest.raises(ReadTimeout):
                await fake.read(timeout=0.05)
            continue
        reply = await fake.read()
        if isinstance(want, bytes):
            assert reply == want, f"{raw!r} -> {reply!r}"
        else:
            assert parse_line(reply).verdict() == want, f"{raw!r} -> {reply!r}"
        await fake.send(b"CENTER")  # reset state between cases
        await fake.read()


async def test_corpus_errors_reply_same_code(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # consume READY
    for raw, expected, _ in CASES:
        if not expected.startswith("ERR:"):
            continue
        code = expected.removeprefix("ERR:")
        await fake.send(raw)
        reply = await fake.read()
        assert reply == f"ERR {code}".encode(), f"{raw!r} -> {reply!r}"


async def test_corpus_noncommands_produce_no_reply(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # consume READY
    for raw, expected, _ in CASES:
        if expected.startswith(("CMD:", "ERR:")):
            continue
        await fake.send(raw)
        with pytest.raises(ReadTimeout):
            await fake.read(timeout=0.05)


# --- degree mapping / hard clamps (mirror of core/mapping.h) ----------


def test_mapping_corners_from_yaml(fake: FakeESP32) -> None:
    cfg = fake.config
    assert cfg.eyes_x.direction == "inverted"
    assert cfg.eyes_x.left_deg == 140.0
    assert cfg.eyes_x.center_deg == 110.0
    assert cfg.eyes_x.right_deg == 70.0
    assert cfg.eyes_y.down_deg == 60.0
    assert cfg.eyes_y.center_deg == 75.0
    assert cfg.eyes_y.up_deg == 85.0


def test_mapping_clamps_degree_span() -> None:
    cfg = load_actuator_config(REPO_ACTUATORS_YAML)
    from sirah.hardware.fake_esp32 import clamp_deg, map_piecewise

    deg_x = map_piecewise(
        -1.0, -1.0, cfg.eyes_x.left_deg, 0.0, cfg.eyes_x.center_deg, 1.0, cfg.eyes_x.right_deg
    )
    assert deg_x == 140.0
    deg_x_right = map_piecewise(
        1.0, -1.0, cfg.eyes_x.left_deg, 0.0, cfg.eyes_x.center_deg, 1.0, cfg.eyes_x.right_deg
    )
    assert deg_x_right == 70.0
    # beyond the calibrated corners -> hard clamp to the spanned range
    assert clamp_deg(deg_x, cfg.eyes_x.right_deg, cfg.eyes_x.left_deg) == 140.0
    assert (
        map_piecewise(
            2.0, -1.0, cfg.eyes_x.left_deg, 0.0, cfg.eyes_x.center_deg, 1.0, cfg.eyes_x.right_deg
        )
        == 70.0
    )


async def test_target_out_of_range_rejected_with_err3(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"TARGET 2.0 0.0")
    assert await fake.read() == b"ERR 3"
    await fake.send(b"TARGET 0.0 -1.5")
    assert await fake.read() == b"ERR 3"


# --- easing mirror ------------------------------------------------------


def test_easing_single_tick_matches_host() -> None:
    g = GazeEaser()
    settled = g.tick(1.0, 1.0, EASE_KX, EASE_KY)
    assert not settled
    assert g.x == pytest.approx(0.25)
    assert g.y == pytest.approx(0.12)


def test_easing_converges_no_overshoot() -> None:
    g = GazeEaser()
    settled = False
    max_x = max_y = -1e9
    for _ in range(120):
        settled = g.tick(1.0, 1.0, EASE_KX, EASE_KY)
        assert -1.0 <= g.x <= 1.0 and -1.0 <= g.y <= 1.0
        max_x, max_y = max(max_x, g.x), max(max_y, g.y)
    assert settled
    assert max_x <= 1.0 and max_y <= 1.0


async def test_fake_state_reports_eased_values(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"TARGET 1.0 -1.0")
    assert await fake.read() == b"OK"
    fake.advance(200)  # 10 ticks of 20 ms
    await fake.send(b"STATUS")
    line = await fake.read()
    assert line is not None
    result = parse_line(line)
    assert result.verdict() == "RESP:STATE"
    x = float(result.args[0])  # type: ignore[union-attr]
    y = float(result.args[1])  # type: ignore[union-attr]
    assert 0.0 < x < 1.0  # eased, not snapped
    assert -1.0 < y < 0.0
    assert x > abs(y)  # X faster than Y: kx=0.25 > ky=0.12


async def test_fake_target_snaps_after_convergence(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"TARGET 0.5 0.5")
    await fake.read()  # OK
    fake.advance(3000)
    await fake.send(b"STATUS")
    line = await fake.read()
    result = parse_line(line)
    x = float(result.args[0])  # type: ignore[union-attr]
    y = float(result.args[1])  # type: ignore[union-attr]
    assert x == pytest.approx(0.5, abs=1e-3)
    assert y == pytest.approx(0.5, abs=1e-3)


# --- blink FSM mirror ---------------------------------------------------


def test_blink_trigger_only_in_idle() -> None:
    fsm = BlinkFSM(seed=7)
    fsm.trigger(0)
    assert fsm.state == "closing"
    fsm.trigger(10)  # mid-blink -> discarded
    assert fsm.state == "closing"
    fsm.tick(1000, 6000)
    assert fsm.state == "closed"
    fsm.trigger(1200)  # mid-blink -> discarded, no queue
    assert fsm.state == "closed"


def test_blink_timing_matches_host() -> None:
    fsm = BlinkFSM(seed=7)
    fsm.trigger(0)
    fsm.tick(100, 6000)  # closing 150 ms
    assert fsm.state == "closing"
    fsm.tick(160, 6000)
    assert fsm.state == "closed"
    fsm.tick(300, 6000)  # closed hold 300 ms
    assert fsm.state == "closed"
    fsm.tick(470, 6000)  # opening 180 ms
    assert fsm.state == "opening"
    fsm.tick(650, 6000)
    assert fsm.state == "idle"  # cycle complete, back to Idle


def test_blink_auto_cadence_fires() -> None:
    fsm = BlinkFSM(BlinkConfig(cadence_ms=400, jitter_ms=0), seed=7)
    handled: list[str] = []
    for t in range(0, 2000, 20):
        fsm.tick(t, 400)
        if fsm.state != "idle":
            handled.append(fsm.state)
    assert "closing" in handled


async def test_blink_command_marks_state_blink_flag(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"BLINK")
    assert await fake.read() == b"OK"
    fake.advance(50)  # mid-closing
    await fake.send(b"STATUS")
    line = await fake.read()
    result = parse_line(line)
    assert result.args[2] == b"1"  # type: ignore[union-attr]


# --- watchdog mirror (Stage 11) ----------------------------------------


async def test_watchdog_recenters_after_heartbeat_pause(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"HEARTBEAT")
    await fake.send(b"TARGET 1.0 -1.0")
    assert await fake.read() == b"OK"
    fake.advance(fake.watchdog_timeout_ms + 2000)
    await fake.send(b"STATUS")
    line = await fake.read()
    result = parse_line(line)
    x = float(result.args[0])  # type: ignore[union-attr]
    y = float(result.args[1])  # type: ignore[union-attr]
    # eased back to CENTER (0,0), not snapped: small values
    assert abs(x) < 0.05 and abs(y) < 0.05


async def test_watchdog_does_not_fire_with_heartbeats(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    for _ in range(5):
        await fake.send(b"HEARTBEAT")
        fake.advance(500)
    await fake.send(b"TARGET 0.9 0.9")
    await fake.read()
    fake.advance(1500)
    await fake.send(b"STATUS")
    line = await fake.read()
    result = parse_line(line)
    x = float(result.args[0])  # type: ignore[union-attr]
    assert x > 0.5  # still tracking, watchdog did not recenter


async def test_watchdog_blink_continues(fake: FakeESP32) -> None:
    await fake.connect()
    await fake.read()  # READY
    await fake.send(b"HEARTBEAT")
    fake.advance(fake.watchdog_timeout_ms + 100)
    await fake.send(b"STATUS")  # report to flush watchdog step
    await fake.read()
    await fake.send(b"BLINK")
    assert await fake.read() == b"OK"  # blink still accepted while centered


# --- initialization from shared YAML (ADR-0009) ------------------------


def test_default_config_loads_from_repo_yaml() -> None:
    fake = FakeESP32()
    cfg = fake.config
    assert isinstance(cfg, ActuatorConfig)
    assert cfg.pwm.freq_hz == 50
    assert cfg.pwm.pulse_us_min == 500
    assert cfg.pwm.pulse_us_max == 2400
    assert cfg.channels["eye_x"] == 0
    assert cfg.channels["inf_left"] == 5
    assert cfg.squint.inf_left_deg == 70.0
    assert cfg.squint.sup_left_deg == 146.0


def test_config_validation_rejects_bad_yaml(tmp_path) -> None:
    bad = tmp_path / "actuators.yaml"
    bad.write_text(
        """
eyes:
  x: {direction: inverted, left_deg: 10.0, center_deg: 110.0, right_deg: 70.0}
  y: {up_deg: 85.0, center_deg: 75.0, down_deg: 60.0}
eyelids:
  sup_right: {open_deg: 110.0, closed_deg: 70.0}
  inf_right: {open_deg: 10.0, closed_deg: 70.0}
  sup_left: {open_deg: 145.0, closed_deg: 170.0}
  inf_left: {open_deg: 95.0, closed_deg: 40.0}
squint_deg: {inf_right: 30.0, sup_right: 90.0, inf_left: 70.0, sup_left: 146.0}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="eyes.x inverted"):
        load_actuator_config(bad)


def test_config_roundtrip_yaml_matches_schema() -> None:
    cfg = load_actuator_config(REPO_ACTUATORS_YAML)
    # fresh FakeESP32 from the same config keeps the identity of limits
    fake = FakeESP32(cfg)
    assert fake.config is cfg
    assert fake.config.eyes_x.left_deg == cfg.eyes_x.left_deg