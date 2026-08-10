"""Consistency check: actuator YAML ↔ firmware calibration.h (ADR-0009).

Firmware calibration.h is the AUTHORITY for physical limits; the actuator
YAML (config/actuators.yaml) is the single runtime-side mirror. This module
parses the header and reports any divergence so contradictory duplication
cannot silently appear (plan Stage 15/16 as a test; wired into
`sirah-calibrate --validate` and `tests/unit/config/` from Stage 7).

The comparison is semantic: corners and pulse range, not formatting.
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

_FLOAT_CONST = re.compile(
    r"inline\s+constexpr\s+(?:float|int)\s+(k\w+)\s*=\s*([0-9.]+)F?"
)

# calibration.h constant name → expected YAML value.
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


def _yaml_value(a: ActuatorConfig, dotted: str) -> float | int:
    """Resolve a dotted path ('eyes_x.left_deg') against ActuatorConfig."""
    obj: object = a
    for part in dotted.split("."):
        if not hasattr(obj, part):
            raise AssertionError(f"consistency: unknown YAML path '{dotted}'")
        obj = getattr(obj, part)
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