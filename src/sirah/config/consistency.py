"""Consistency checks: actuator YAML ↔ firmware calibration.h and pins.h.

Firmware files are the AUTHORITY for physical limits and wiring: the
actuator YAML (config/actuators.yaml) is the single runtime-side mirror.
This module parses both headers and reports any divergence so
contradictory duplication cannot silently appear (plan Stage 15/16 as a
test; wired into `sirah-calibrate --validate` and `tests/unit/config/`
from Stage 7).

The comparison is semantic: corners/pulse range/channels, not formatting.
"""

from __future__ import annotations

import re
from pathlib import Path

from sirah.config.schema import ActuatorConfig, load_actuator_config

_DEFAULT_CALIB_H = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "sirah-eyes"
    / "config"
    / "calibration.h"
)

_DEFAULT_PINS_H = (
    Path(__file__).resolve().parents[3]
    / "firmware"
    / "sirah-eyes"
    / "platform"
    / "pins.h"
)

_FLOAT_CONST = re.compile(
    r"inline\s+constexpr\s+(?:float|int)\s+(k\w+)\s*=\s*([0-9.]+)F?"
)

_INT_CONST = re.compile(
    r"inline\s+constexpr\s+int\s+(k\w+)\s*=\s*(0[xX][0-9a-fA-F]+|\d+)\s*;"
)

# calibration.h constant name → expected YAML path and kind.
_EXPECTED: dict[str, tuple[str, str]] = {
    "kPwmUsMin": ("pwm.pulse_us_min", "int"),
    "kPwmUsMax": ("pwm.pulse_us_max", "int"),
    "kEyeXLeftDeg": ("eyes_x.left_deg", "float"),
    "kEyeXCenterDeg": ("eyes_x.center_deg", "float"),
    "kEyeXRightDeg": ("eyes_x.right_deg", "float"),
    "kEyeYUpDeg": ("eyes_y.up_deg", "float"),
    "kEyeYCenterDeg": ("eyes_y.center_deg", "float"),
    "kEyeYDownDeg": ("eyes_y.down_deg", "float"),
    "kEyelidSupRightOpenDeg": ("eyelids.sup_right.open_deg", "float"),
    "kEyelidSupRightClosedDeg": ("eyelids.sup_right.closed_deg", "float"),
    "kEyelidInfRightOpenDeg": ("eyelids.inf_right.open_deg", "float"),
    "kEyelidInfRightClosedDeg": ("eyelids.inf_right.closed_deg", "float"),
    "kEyelidSupLeftOpenDeg": ("eyelids.sup_left.open_deg", "float"),
    "kEyelidSupLeftClosedDeg": ("eyelids.sup_left.closed_deg", "float"),
    "kEyelidInfLeftOpenDeg": ("eyelids.inf_left.open_deg", "float"),
    "kEyelidInfLeftClosedDeg": ("eyelids.inf_left.closed_deg", "float"),
    "kSquintInfRightDeg": ("squint.inf_right_deg", "float"),
    "kSquintSupRightDeg": ("squint.sup_right_deg", "float"),
    "kSquintInfLeftDeg": ("squint.inf_left_deg", "float"),
    "kSquintSupLeftDeg": ("squint.sup_left_deg", "float"),
}


# pins.h constant name → expected YAML path and kind (hex: 0x-addresses).
_PINS_EXPECTED: dict[str, tuple[str, str]] = {
    "kPwmChannelEyeX": ("channels.eye_x", "int"),
    "kPwmChannelEyeY": ("channels.eye_y", "int"),
    "kPwmChannelEyelidSupRight": ("channels.sup_right", "int"),
    "kPwmChannelEyelidInfRight": ("channels.inf_right", "int"),
    "kPwmChannelEyelidSupLeft": ("channels.sup_left", "int"),
    "kPwmChannelEyelidInfLeft": ("channels.inf_left", "int"),
    "kPwmI2cSda": ("pwm.i2c_sda", "int"),
    "kPwmI2cScl": ("pwm.i2c_scl", "int"),
    "kPwmI2cAddr": ("pwm.i2c_address", "hex"),
}


def _yaml_raw(a: object, dotted: str) -> object:
    """Resolve a dotted path ('eyes_x.left_deg' or 'channels.eye_x')."""
    obj: object = a
    for part in dotted.split("."):
        if isinstance(obj, dict):
            if part not in obj:
                raise AssertionError(f"consistency: unknown YAML key '{part}' in '{dotted}'")
            obj = obj[part]
        else:
            if not hasattr(obj, part):
                raise AssertionError(f"consistency: unknown YAML path '{dotted}'")
            obj = getattr(obj, part)
    return obj


def _yaml_value(a: ActuatorConfig, dotted: str) -> float | int:
    """Resolve a dotted path ('eyes_x.left_deg') against ActuatorConfig."""
    obj = _yaml_raw(a, dotted)
    assert isinstance(obj, (float, int)), f"consistency: '{dotted}' is not numeric"
    return obj


def parse_calibration_header(path: str | Path | None = None) -> dict[str, float]:
    """Extract instrumented constants from calibration.h (name → value)."""
    header_path = Path(path) if path is not None else _DEFAULT_CALIB_H
    if not header_path.exists():
        raise FileNotFoundError(f"calibration.h not found: {header_path}")
    values: dict[str, float] = {}
    for line in header_path.read_text(encoding="utf-8").splitlines():
        match = _FLOAT_CONST.search(line)
        if match:
            values[match.group(1)] = float(match.group(2))
    return values


def validate_actuator_mirror(
    actuators: ActuatorConfig,
    header_path: str | Path | None = None,
) -> list[str]:
    """Return a list of discrepancies YAML-vs-header (empty = consistent).

    Each string describes one divergence with both values. Firmware header
    is the authority: a mismatch means the YAML mirror is stale.
    """
    header = parse_calibration_header(header_path)
    problems: list[str] = []
    for constant, (dotted, kind) in _EXPECTED.items():
        if constant not in header:
            problems.append(f"calibration.h is missing '{constant}'")
            continue
        header_value = header[constant]
        yaml_value = _yaml_value(actuators, dotted)
        expected = int(header_value) if kind == "int" else round(header_value, 6)
        if yaml_value != expected:
            problems.append(
                f"{constant} ({dotted}): header={header_value:g} "
                f"vs actuators.yaml={yaml_value:g}"
            )
    return problems


def verify_mirror_files(
    yaml_path: str | Path | None = None,
    header_path: str | Path | None = None,
) -> list[str]:
    """Convenience: load both files and run the consistency check."""
    return validate_actuator_mirror(load_actuator_config(yaml_path), header_path)


def parse_pins_header(path: str | Path | None = None) -> dict[str, int]:
    """Extract instrumented constants from pins.h (name → value, hex decoded)."""
    pins_path = Path(path) if path is not None else _DEFAULT_PINS_H
    if not pins_path.exists():
        raise FileNotFoundError(f"pins.h not found: {pins_path}")
    values: dict[str, int] = {}
    for line in pins_path.read_text(encoding="utf-8").splitlines():
        match = _INT_CONST.search(line)
        if match:
            raw = match.group(2)
            values[match.group(1)] = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    return values


def validate_pins_mirror(
    actuators: ActuatorConfig,
    pins_path: str | Path | None = None,
) -> list[str]:
    """Return a list of discrepancies YAML-vs-pins.h (empty = consistent).

    pins.h owns the physical wiring (ADR-0011): PCA9685 channels and the
    I2C bus map. A mismatch means the YAML mirror (or the header) drifted.
    """
    header = parse_pins_header(pins_path)
    problems: list[str] = []
    for constant, (dotted, kind) in _PINS_EXPECTED.items():
        if constant not in header:
            problems.append(f"pins.h is missing '{constant}'")
            continue
        header_value = header[constant]
        if kind == "hex":
            mirrored: float | int = int(str(_yaml_raw(actuators, dotted)), 16)
            if header_value != mirrored:
                problems.append(
                    f"{constant} ({dotted}): pins.h=0x{header_value:x} "
                    f"vs actuators.yaml=0x{mirrored:x}"
                )
        else:
            mirrored = _yaml_value(actuators, dotted)
            if header_value != mirrored:
                problems.append(
                    f"{constant} ({dotted}): pins.h={header_value} "
                    f"vs actuators.yaml={mirrored:g}"
                )
    return problems


def verify_pins_files(
    yaml_path: str | Path | None = None,
    pins_path: str | Path | None = None,
) -> list[str]:
    """Convenience: load the YAML and pins.h, run the pins mirror check."""
    return validate_pins_mirror(load_actuator_config(yaml_path), pins_path)