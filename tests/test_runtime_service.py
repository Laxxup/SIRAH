"""Tests for the server-only runtime service entrypoint."""

from __future__ import annotations

import asyncio
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest

from sirah.errors import RuntimeConfigurationError
from sirah.factory import SystemProfile
from sirah.runtime_service import RuntimeServiceConfig, run_runtime
from sirah.types import ClientKind


def _environment(**overrides: str) -> dict[str, str]:
    environment = {
        "SIRAH_RUNTIME_SOCKET": "/run/sirah/runtime.sock",
        "SIRAH_RUNTIME_CLI_SECRET": "cli-server-secret",
        "SIRAH_RUNTIME_WEB_LAB_SECRET": "web-server-secret",
        "SIRAH_RUNTIME_PROFILE": "dev_laptop",
        "SIRAH_RUNTIME_CAPTURE_DEVICES": "mic-primary,mic-backup",
        "SIRAH_RUNTIME_CAPTURE_DEVICE": "mic-primary",
        "SIRAH_RUNTIME_OUTPUT_DEVICES": "speaker-primary",
        "SIRAH_RUNTIME_OUTPUT_DEVICE": "speaker-primary",
    }
    environment.update(overrides)
    return environment


def test_runtime_service_reads_only_server_environment_configuration() -> None:
    config = RuntimeServiceConfig.from_environment(_environment())

    assert config.socket_path == Path("/run/sirah/runtime.sock")
    assert config.profile is SystemProfile.DEV_LAPTOP
    assert config.client_secrets == {
        ClientKind.CLI: "cli-server-secret",
        ClientKind.WEB_LAB: "web-server-secret",
    }
    assert config.capture_devices == ("mic-primary", "mic-backup")
    assert config.capture_device == "mic-primary"
    assert config.output_devices == ("speaker-primary",)
    assert config.output_device == "speaker-primary"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SIRAH_RUNTIME_SOCKET": ""}, "SIRAH_RUNTIME_SOCKET"),
        ({"SIRAH_RUNTIME_CLI_SECRET": ""}, "SIRAH_RUNTIME_CLI_SECRET"),
        ({"SIRAH_RUNTIME_PROFILE": "production"}, "SIRAH_RUNTIME_PROFILE"),
        ({"SIRAH_RUNTIME_CAPTURE_DEVICES": ""}, "SIRAH_RUNTIME_CAPTURE_DEVICES"),
        ({"SIRAH_RUNTIME_CAPTURE_DEVICE": "unknown"}, "capture device"),
        ({"SIRAH_RUNTIME_OUTPUT_DEVICES": ""}, "SIRAH_RUNTIME_OUTPUT_DEVICES"),
        ({"SIRAH_RUNTIME_OUTPUT_DEVICE": "unknown"}, "output device"),
    ],
)
def test_runtime_service_rejects_invalid_server_configuration(
    overrides: Mapping[str, str], message: str
) -> None:
    with pytest.raises(RuntimeConfigurationError, match=message):
        RuntimeServiceConfig.from_environment(_environment(**overrides))


def test_runtime_service_configuration_error_never_includes_secret() -> None:
    secret = "do-not-disclose-this-secret"

    with pytest.raises(RuntimeConfigurationError) as error:
        RuntimeServiceConfig.from_environment(
            _environment(SIRAH_RUNTIME_PROFILE="production", SIRAH_RUNTIME_CLI_SECRET=secret)
        )

    assert secret not in str(error.value)


def test_runtime_service_rejects_partial_or_unreadable_piper_configuration(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeConfigurationError, match="Piper config"):
        RuntimeServiceConfig.from_environment(
            _environment(SIRAH_RUNTIME_PIPER_MODEL=str(tmp_path / "missing.onnx"))
        )

    model = tmp_path / "voice.onnx"
    model.touch()
    with pytest.raises(RuntimeConfigurationError, match="Piper config"):
        RuntimeServiceConfig.from_environment(
            _environment(SIRAH_RUNTIME_PIPER_MODEL=str(model))
        )


@pytest.mark.asyncio
async def test_runtime_service_stops_runtime_after_shutdown_signal() -> None:
    events: list[str] = []
    shutdown = asyncio.Event()
    shutdown.set()

    class Runtime:
        async def start(self) -> None:
            events.append("start")

        async def stop(self) -> None:
            events.append("stop")

    await run_runtime(
        RuntimeServiceConfig.from_environment(_environment()),
        runtime_factory=lambda _: Runtime(),
        shutdown_event=shutdown,
    )

    assert events == ["start", "stop"]


def test_package_registers_runtime_service_entrypoint() -> None:
    with Path("pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    assert project["project"]["scripts"]["sirah-runtime"] == "sirah.runtime_service:cli"


def test_deployment_script_prepares_python_314_runtime_and_optional_web_client() -> None:
    deployment = Path("scripts/deploy_pi.sh").read_text()
    runtime_environment = Path("deploy/systemd/runtime.env.example").read_text()
    web_environment = Path("deploy/systemd/web-lab.env.example").read_text()

    assert "python3.14" in deployment
    assert 'command -v "$PYTHON"' in deployment
    assert "Python 3.14 is required" in deployment
    assert "apt-get" not in deployment
    assert "sirah-runtime.service" in deployment
    assert "sirah-web-lab.service" in deployment
    assert "SIRAH_RUNTIME_CLI_SECRET" in runtime_environment
    assert "SIRAH_RUNTIME_WEB_LAB_SECRET" in runtime_environment
    assert "SIRAH_WEB_LAB_SECRET" in web_environment
    assert "systemctl start" not in deployment
    assert "--intel=" not in deployment
    assert "--tts=" not in deployment


def test_service_documentation_avoids_absent_smokes_and_example_directories() -> None:
    piper_documentation = Path("docs/piper.md").read_text()
    contributing = Path("CONTRIBUTING.md").read_text()

    assert "examples/piper_smoke.py" not in piper_documentation
    assert "SIRAH_RUN_PIPER_SMOKE" not in piper_documentation
    assert "ruff check src tests examples" not in contributing
