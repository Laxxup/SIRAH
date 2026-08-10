"""Consistency tests: actuators.yaml must mirror firmware calibration.h.

ADR-0009: calibration.h is the authority; the YAML is the single
runtime-side mirror. These tests pin the repo pair so no contradictory
duplication can silently appear (plan Stage 7 wiring, formalized in
Stage 15/16).
"""

from __future__ import annotations

from pathlib import Path

from sirah.config.consistency import (
    parse_calibration_header,
    parse_pins_header,
    validate_actuator_mirror,
    validate_pins_mirror,
    verify_mirror_files,
    verify_pins_files,
)

HEADER_PATH = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "sirah-eyes"
    / "config"
    / "calibration.h"
)
PINS_PATH = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "sirah-eyes"
    / "platform"
    / "pins.h"
)
YAML_PATH = Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"


def test_repo_mirror_is_consistent():
    problems = verify_mirror_files(YAML_PATH, HEADER_PATH)
    assert problems == [], "\n".join(problems)


def test_header_parser_extracts_key_constants():
    values = parse_calibration_header(HEADER_PATH)
    assert values["kPwmUsMin"] == 500
    assert values["kPwmUsMax"] == 2400
    assert values["kEyeXLeftDeg"] == 140.0
    assert values["kEyeXRightDeg"] == 70.0
    assert values["kSquintSupLeftDeg"] == 146.0
    assert values["kEyelidInfLeftOpenDeg"] == 95.0


def test_divergence_is_detected(monkeypatch):
    from sirah.config import schema as schema_mod

    problems = validate_actuator_mirror(schema_mod.load_actuator_config(YAML_PATH), HEADER_PATH)
    assert problems == []
    # Now corrupt the header side: pretend the authority moved a corner.
    header = parse_calibration_header(HEADER_PATH)
    header["kEyeXLeftDeg"] = 141.0
    monkeypatch.setattr(
        "sirah.config.consistency.parse_calibration_header",
        lambda *a, **k: header,
    )
    problems = validate_actuator_mirror(schema_mod.load_actuator_config(YAML_PATH))
    assert any("kEyeXLeftDeg" in p for p in problems)


def test_repo_pins_mirror_is_consistent():
    problems = verify_pins_files(YAML_PATH, PINS_PATH)
    assert problems == [], "\n".join(problems)


def test_pins_parser_extracts_channels_and_i2c():
    values = parse_pins_header(PINS_PATH)
    assert values["kPwmChannelEyeX"] == 0
    assert values["kPwmChannelEyeY"] == 1
    assert values["kPwmChannelEyelidInfLeft"] == 5
    assert values["kPwmI2cSda"] == 21
    assert values["kPwmI2cScl"] == 22
    assert values["kPwmI2cAddr"] == 0x40


def test_pins_divergence_is_detected(monkeypatch):
    from sirah.config import schema as schema_mod

    problems = validate_pins_mirror(schema_mod.load_actuator_config(YAML_PATH), PINS_PATH)
    assert problems == []
    # Corrupt the header side: pretend a channel moved on the board.
    header = parse_pins_header(PINS_PATH)
    header["kPwmChannelEyeX"] = 7
    monkeypatch.setattr(
        "sirah.config.consistency.parse_pins_header",
        lambda *a, **k: header,
    )
    problems = validate_pins_mirror(schema_mod.load_actuator_config(YAML_PATH))
    assert any("kPwmChannelEyeX" in p for p in problems)