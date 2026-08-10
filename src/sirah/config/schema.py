"""Actuator config schema + loaded (config/actuators.yaml, ADR-0009).

Shared PC-side mirror of firmware calibration.h: one place the runtime,
the fake and tooling read physical limits from. Firmware remains the
AUTHORITY; a consistency test (Stage 15/16) pins this YAML to the header.

Loader: pydantic not used (base install zero deps) — a small hand-rolled
parser with validation keeps the runtime dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Anchors A1: X -1 left / 0 center / +1 right; Y -1 down / 0 center / +1 up.
_DEFAULT_ACTUATORS_YAML = (
    Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"
)


@dataclass(frozen=True)
class EyeXConfig:
    direction: str  # "inverted" | "normal" — physical servo inversion is data
    left_deg: float
    center_deg: float
    right_deg: float


@dataclass(frozen=True)
class EyeYConfig:
    direction: str
    up_deg: float
    center_deg: float
    down_deg: float


@dataclass(frozen=True)
class EyelidConfig:
    open_deg: float
    closed_deg: float


@dataclass(frozen=True)
class EyelidsConfig:
    sup_right: EyelidConfig
    inf_right: EyelidConfig
    sup_left: EyelidConfig
    inf_left: EyelidConfig


@dataclass(frozen=True)
class SquintConfig:
    inf_right_deg: float
    sup_right_deg: float
    inf_left_deg: float
    sup_left_deg: float


@dataclass(frozen=True)
class PwmConfig:
    freq_hz: int
    pulse_us_min: int
    pulse_us_max: int
    i2c_sda: int
    i2c_scl: int
    i2c_address: str


@dataclass(frozen=True)
class ActuatorConfig:
    eyes_x: EyeXConfig
    eyes_y: EyeYConfig
    eyelids: EyelidsConfig
    squint: SquintConfig
    pwm: PwmConfig
    channels: dict[str, int] = field(default_factory=dict)


def _require(d: dict, key: str, where: str) -> object:
    if key not in d:
        raise ValueError(f"actuators.yaml: missing '{key}' in {where}")
    return d[key]


def _require_float(d: dict, key: str, where: str) -> float:
    value = _require(d, key, where)
    try:
        return float(str(value))
    except ValueError as exc:
        raise ValueError(f"actuators.yaml: '{key}' in {where} must be a number") from exc


def _parse_channels(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise TypeError("actuators.yaml: 'channels' must be a mapping")
    channels: dict[str, int] = {}
    for name, ch in raw.items():
        try:
            channels[str(name)] = int(str(ch))
        except ValueError as exc:
            raise ValueError(f"actuators.yaml: channel '{name}' must be an int") from exc
    return channels


def load_actuator_config(path: str | Path | None = None) -> ActuatorConfig:
    """Load config/actuators.yaml (defaults to the repository baseline).

    Validates the A1 corner conventions: X corners must span center with
    left/right around it; inverted X means left > center > right, normal
    means left < center < right. Y corners must satisfy A1 (down < center
    < up). Raises ValueError with a clear message on violations.
    """
    yaml_path = Path(path) if path is not None else _DEFAULT_ACTUATORS_YAML
    with yaml_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    eyes = data.get("eyes", {})
    if not isinstance(eyes, dict) or not isinstance(eyes.get("x"), dict) or not isinstance(eyes.get("y"), dict):
        raise TypeError("actuators.yaml: 'eyes.x' and 'eyes.y' sections are required")

    eyes_x_raw: dict = eyes["x"]
    eyes_y_raw: dict = eyes["y"]

    eye_x = EyeXConfig(
        direction=str(eyes_x_raw.get("direction", "normal")),
        left_deg=_require_float(eyes_x_raw, "left_deg", "eyes.x"),
        center_deg=_require_float(eyes_x_raw, "center_deg", "eyes.x"),
        right_deg=_require_float(eyes_x_raw, "right_deg", "eyes.x"),
    )
    eye_y = EyeYConfig(
        direction=str(eyes_y_raw.get("direction", "normal")),
        up_deg=_require_float(eyes_y_raw, "up_deg", "eyes.y"),
        center_deg=_require_float(eyes_y_raw, "center_deg", "eyes.y"),
        down_deg=_require_float(eyes_y_raw, "down_deg", "eyes.y"),
    )

    _validate_conventions(eye_x, eye_y)

    eyelids_raw = data.get("eyelids", {})
    eyelid_names = ("sup_right", "inf_right", "sup_left", "inf_left")
    eyelid_configs: dict[str, EyelidConfig] = {}
    for name in eyelid_names:
        section = eyelids_raw.get(name, {})
        if not isinstance(section, dict):
            raise TypeError(f"actuators.yaml: 'eyelids.{name}' section is required")
        eyelid_configs[name] = EyelidConfig(
            open_deg=_require_float(section, "open_deg", f"eyelids.{name}"),
            closed_deg=_require_float(section, "closed_deg", f"eyelids.{name}"),
        )
    eyelids = EyelidsConfig(**eyelid_configs)

    squint_raw = data.get("squint_deg", {})
    squint = SquintConfig(
        inf_right_deg=_require_float(squint_raw, "inf_right", "squint_deg"),
        sup_right_deg=_require_float(squint_raw, "sup_right", "squint_deg"),
        inf_left_deg=_require_float(squint_raw, "inf_left", "squint_deg"),
        sup_left_deg=_require_float(squint_raw, "sup_left", "squint_deg"),
    )

    pwm_raw = data.get("pwm", {})
    pulse = pwm_raw.get("pulse_us", {})
    i2c = pwm_raw.get("i2c", {})
    pwm = PwmConfig(
        freq_hz=int(_require_float(pwm_raw, "freq_hz", "pwm")),
        pulse_us_min=int(_require_float(pulse, "min", "pwm.pulse_us")),
        pulse_us_max=int(_require_float(pulse, "max", "pwm.pulse_us")),
        i2c_sda=int(_require_float(i2c, "sda", "pwm.i2c")),
        i2c_scl=int(_require_float(i2c, "scl", "pwm.i2c")),
        i2c_address=str(_require(i2c, "address", "pwm.i2c")),
    )

    channels = _parse_channels(data.get("channels", {}))

    return ActuatorConfig(
        eyes_x=eye_x,
        eyes_y=eye_y,
        eyelids=eyelids,
        squint=squint,
        pwm=pwm,
        channels=channels,
    )


def _validate_conventions(eye_x: EyeXConfig, eye_y: EyeYConfig) -> None:
    """A1 corner convention validation (implementation detail)."""
    if eye_x.direction == "inverted" and not (
        eye_x.left_deg > eye_x.center_deg > eye_x.right_deg
    ):
        raise ValueError(
            "actuators.yaml: eyes.x inverted requires left > center > right "
            f"(got {eye_x.left_deg}, {eye_x.center_deg}, {eye_x.right_deg})"
        )
    if eye_x.direction == "normal" and not (
        eye_x.left_deg < eye_x.center_deg < eye_x.right_deg
    ):
        raise ValueError(
            "actuators.yaml: eyes.x normal requires left < center < right "
            f"(got {eye_x.left_deg}, {eye_x.center_deg}, {eye_x.right_deg})"
        )
    if not (eye_y.down_deg < eye_y.center_deg < eye_y.up_deg):
        raise ValueError(
            "actuators.yaml: eyes.y (A1) requires down < center < up "
            f"(got {eye_y.down_deg}, {eye_y.center_deg}, {eye_y.up_deg})"
        )