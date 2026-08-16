"""Runtime settings loader tests (Stage 7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sirah.config.loader import (
    DEFAULT_SERIAL_DEVICE,
    RuntimeSettings,
    load_runtime_config,
    load_runtime_settings,
)

REPO_RUNTIME_TOML = Path(__file__).resolve().parents[3] / "config" / "runtime.toml"
REPO_ACTUATORS_YAML = Path(__file__).resolve().parents[3] / "config" / "actuators.yaml"


def test_defaults_from_repo_baseline():
    settings = load_runtime_settings(REPO_RUNTIME_TOML)
    assert settings.serial_device == DEFAULT_SERIAL_DEVICE
    assert settings.baudrate == 115200
    assert settings.eyes_armed is False  # legacy default: disarmed
    assert settings.heartbeat_cadence_s == 1.0
    assert settings.heartbeat_timeout_s == 3.0
    assert settings.read_timeout_s == 1.0
    assert settings.lost_face_center_s == 2.0


def test_env_overrides_device_and_arm():
    env = {"SIRAH_SERIAL_DEVICE": "/dev/sirah-eyes", "SIRAH_EYES": "1"}
    settings = load_runtime_settings(REPO_RUNTIME_TOML, env)
    assert settings.serial_device == "/dev/sirah-eyes"
    assert settings.eyes_armed is True


def test_env_eye_zero_disarms_even_when_toml_armed():
    env = {"SIRAH_EYES": "0"}
    settings = load_runtime_settings(REPO_RUNTIME_TOML, env)
    assert settings.eyes_armed is False


def test_allowlist():
    assert load_runtime_settings(REPO_RUNTIME_TOML).serial_device_is_allowlisted
    env = {"SIRAH_SERIAL_DEVICE": "/dev/ttyUSB0"}
    assert load_runtime_settings(REPO_RUNTIME_TOML, env).serial_device_is_allowlisted
    env = {"SIRAH_SERIAL_DEVICE": "/tmp/evil"}
    assert not load_runtime_settings(REPO_RUNTIME_TOML, env).serial_device_is_allowlisted


def test_load_runtime_config_absorbs_actuator_yaml():
    settings, actuators = load_runtime_config(
        REPO_RUNTIME_TOML, REPO_ACTUATORS_YAML
    )
    assert settings.eyes_armed is False
    assert actuators.eyes_x.direction == "inverted"
    assert actuators.pwm.pulse_us_min == 500
    assert actuators.pwm.pulse_us_max == 2400


def test_missing_toml_raises():
    with pytest.raises(FileNotFoundError):
        load_runtime_settings("/tmp/does-not-exist.toml")


def test_runtime_settings_default_is_disarmed():
    settings = RuntimeSettings()
    assert settings.eyes_armed is False


def test_eyes_section_without_armed_remains_disarmed(tmp_path):
    toml = tmp_path / "runtime.toml"
    toml.write_text(
        "[eyes]\n"
        'device = "/dev/ttyUSB0"\n'
        "baudrate = 115200\n"
        "read_timeout_s = 1.0\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings(toml, env={})

    assert settings.eyes_armed is False


def test_runtime_settings_rejects_non_positive_tick():
    with pytest.raises(ValueError, match="tick_s must be positive"):
        RuntimeSettings(tick_s=0)
    with pytest.raises(ValueError, match="tick_s must be positive"):
        RuntimeSettings(tick_s=-0.5)
