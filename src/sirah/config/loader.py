"""Runtime settings + actuator config unified loading (ADR-0009).

TOML for runtime settings, YAML for actuators/calibration (decision A9).
This module absorbs the actuator loader from schema.py: the runtime and
tooling always load BOTH so the actuator YAML stays the single mirror of
firmware calibration.h. Env vars SIRAH_* override TOML (Global
Constraints): SIRAH_SERIAL_DEVICE, SIRAH_EYES, SIRAH_LAB, SIRAH_HIL.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sirah.config.schema import ActuatorConfig, load_actuator_config

_DEFAULT_RUNTIME_TOML = Path(__file__).resolve().parents[3] / "config" / "runtime.toml"
_DEFAULT_ACTUATORS_YAML = Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"

DEFAULT_SERIAL_DEVICE = "/dev/ttyUSB0"


@dataclass(frozen=True)
class RuntimeSettings:
    """Runtime settings mirroring config/runtime.toml (ADR-0009)."""

    serial_device: str = DEFAULT_SERIAL_DEVICE
    baudrate: int = 115200
    eyes_armed: bool = True  # SIRAH_EYES: 0 disarms the eyes subsystem
    heartbeat_cadence_s: float = 1.0  # proposed 1 s cadence (Stage 11/A2)
    heartbeat_timeout_s: float = 3.0  # proposed 3 s timeout (Stage 11/A2)
    lost_face_center_s: float = 2.0
    tick_s: float = 0.02
    lab_enabled: bool = False  # ADR-0007; SIRAH_LAB
    env: dict[str, str] = field(default_factory=dict)

    @property
    def serial_device_is_allowlisted(self) -> bool:
        """ADR-0002/legacy allowlist: /dev/ttyUSB* or /dev/sirah-eyes."""
        return self.serial_device.startswith("/dev/ttyUSB") or (
            self.serial_device == "/dev/sirah-eyes"
        )


def _env_bool(env: dict[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip() in ("1", "true", "yes", "on")


def _env_str(env: dict[str, str], key: str, default: str | None) -> str | None:
    raw = env.get(key)
    return raw if raw is not None and raw.strip() else default


def load_runtime_settings(
    toml_path: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> RuntimeSettings:
    """Load config/runtime.toml (defaults to the repository baseline).

    Env overrides (Global Constraints): SIRAH_SERIAL_DEVICE overrides the
    serial device; SIRAH_EYES=0 disarms eyes; SIRAH_LAB=1 enables the
    laboratory proposal gate off by default (ADR-0007).
    """
    path = Path(toml_path) if toml_path is not None else _DEFAULT_RUNTIME_TOML
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    env = env or dict(os.environ)
    eyes = data.get("eyes", {})
    heartbeat = data.get("heartbeat", {})
    behavior = data.get("behavior", {})

    device = _env_str(env, "SIRAH_SERIAL_DEVICE", None) or str(
        eyes.get("device", DEFAULT_SERIAL_DEVICE)
    )
    settings = RuntimeSettings(
        serial_device=device,
        baudrate=int(eyes.get("baudrate", 115200)),
        eyes_armed=_env_bool(env, "SIRAH_EYES", bool(eyes.get("armed", True))),
        heartbeat_cadence_s=float(heartbeat.get("cadence_s", 1.0)),
        heartbeat_timeout_s=float(heartbeat.get("timeout_s", 3.0)),
        lost_face_center_s=float(behavior.get("lost_face_center_s", 2.0)),
        tick_s=float(data.get("tick_s", 0.02)),
        lab_enabled=_env_bool(env, "SIRAH_LAB", bool(data.get("lab", {}).get("enabled", False))),
        env=dict(env),
    )
    return settings


def load_runtime_config(
    runtime_toml: str | Path | None = None,
    actuators_yaml: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[RuntimeSettings, ActuatorConfig]:
    """Load runtime settings + actuator mirror together (ADR-0009).

    The single entry point the CLI and app use: the actuator YAML is
    ALWAYS validated next to the runtime settings so a contradictory
    duplication cannot silently appear (consistency test lives in
    tests/unit/config/).
    """
    settings = load_runtime_settings(runtime_toml, env)
    yaml_path = Path(actuators_yaml) if actuators_yaml else _DEFAULT_ACTUATORS_YAML
    actuators = load_actuator_config(yaml_path)
    return settings, actuators