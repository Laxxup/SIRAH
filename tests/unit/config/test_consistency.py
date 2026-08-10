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
    validate_actuator_mirror,
    verify_mirror_files,
)

HEADER_PATH = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "sirah-eyes"
    / "config"
    / "calibration.h"
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