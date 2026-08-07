"""Server-only entrypoint for the headless SIRAH runtime."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sirah.core.devices import DeviceRegistry
from sirah.core.runtime import SirahRuntime
from sirah.errors import RuntimeConfigurationError
from sirah.factory import SystemProfile
from sirah.types import ClientKind

__all__ = ["RuntimeServiceConfig", "cli", "main", "run_runtime"]


class RuntimeLifecycle(Protocol):
    """The lifecycle owned by the service process."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeServiceConfig:
    """Validated configuration supplied exclusively by the service environment."""

    socket_path: Path
    client_secrets: Mapping[ClientKind, str]
    profile: SystemProfile
    capture_devices: tuple[str, ...]
    capture_device: str
    output_devices: tuple[str, ...]
    output_device: str
    piper_model_path: Path | None = None
    piper_config_path: Path | None = None
    intelligence_type: str = "fake"
    ollama_base_url: str | None = None
    ollama_model: str = "gpt-oss:120b-cloud"
    ollama_fallback_model: str | None = "gemma3:4b"
    ollama_timeout: float = 30.0
    kokoro_url: str | None = None
    kokoro_model: str = "kokoro"
    kokoro_voice: str = "ef_dora"
    kokoro_speed: float = 1.0
    kokoro_timeout: float = 30.0
    tts: str = "fake"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> RuntimeServiceConfig:
        socket_path = Path(_required(environment, "SIRAH_RUNTIME_SOCKET"))
        if not socket_path.is_absolute():
            raise RuntimeConfigurationError("SIRAH_RUNTIME_SOCKET must be an absolute path")
        profile = _profile(_required(environment, "SIRAH_RUNTIME_PROFILE"))
        capture_devices = _devices(environment, "SIRAH_RUNTIME_CAPTURE_DEVICES")
        capture_device = _required(environment, "SIRAH_RUNTIME_CAPTURE_DEVICE")
        output_devices = _devices(environment, "SIRAH_RUNTIME_OUTPUT_DEVICES")
        output_device = _required(environment, "SIRAH_RUNTIME_OUTPUT_DEVICE")
        if capture_device not in capture_devices:
            raise RuntimeConfigurationError("configured capture device is not allowed")
        if output_device not in output_devices:
            raise RuntimeConfigurationError("configured output device is not allowed")
        piper_model_path, piper_config_path = _piper_paths(environment)
        return cls(
            socket_path=socket_path,
            client_secrets={
                ClientKind.CLI: _required(environment, "SIRAH_RUNTIME_CLI_SECRET"),
                ClientKind.WEB_LAB: _required(
                    environment, "SIRAH_RUNTIME_WEB_LAB_SECRET"
                ),
            },
            profile=profile,
            capture_devices=capture_devices,
            capture_device=capture_device,
            output_devices=output_devices,
            output_device=output_device,
            piper_model_path=piper_model_path,
            piper_config_path=piper_config_path,
            intelligence_type=environment.get("SIRAH_LLM_PROVIDER", "fake"),
            ollama_base_url=environment.get("SIRAH_OLLAMA_URL"),
            ollama_model=environment.get("SIRAH_OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            ollama_fallback_model=environment.get(
                "SIRAH_OLLAMA_FALLBACK_MODEL", "gemma3:4b"
            ) or None,
            ollama_timeout=float(environment.get("SIRAH_OLLAMA_TIMEOUT", "30.0")),
            kokoro_url=environment.get("SIRAH_KOKORO_URL"),
            kokoro_model=environment.get("SIRAH_KOKORO_MODEL", "kokoro"),
            kokoro_voice=environment.get("SIRAH_KOKORO_VOICE", "ef_dora"),
            kokoro_speed=float(environment.get("SIRAH_KOKORO_SPEED", "1.0")),
            kokoro_timeout=float(environment.get("SIRAH_KOKORO_TIMEOUT", "30.0")),
            tts=environment.get("SIRAH_TTS_PROVIDER", "fake"),
        )


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RuntimeConfigurationError(f"{name} must be configured")
    return value


def _devices(environment: Mapping[str, str], name: str) -> tuple[str, ...]:
    devices = tuple(device.strip() for device in _required(environment, name).split(","))
    if not all(devices) or len(set(devices)) != len(devices):
        raise RuntimeConfigurationError(f"{name} must be a unique comma-separated list")
    return devices


def _profile(value: str) -> SystemProfile:
    profiles = {
        "dev_laptop": SystemProfile.DEV_LAPTOP,
        "dev_distributed": SystemProfile.DEV_DISTRIBUTED,
    }
    try:
        return profiles[value]
    except KeyError as error:
        raise RuntimeConfigurationError("SIRAH_RUNTIME_PROFILE is invalid") from error


def _piper_paths(environment: Mapping[str, str]) -> tuple[Path | None, Path | None]:
    model = environment.get("SIRAH_RUNTIME_PIPER_MODEL", "").strip()
    config = environment.get("SIRAH_RUNTIME_PIPER_CONFIG", "").strip()
    if not model and not config:
        return None, None
    if not model:
        raise RuntimeConfigurationError("Piper model must be configured")
    if not config:
        raise RuntimeConfigurationError("Piper config must be configured")
    model_path = Path(model)
    config_path = Path(config)
    if not model_path.is_file() or not os.access(model_path, os.R_OK):
        raise RuntimeConfigurationError("Piper model is not a readable file")
    if not config_path.is_file() or not os.access(config_path, os.R_OK):
        raise RuntimeConfigurationError("Piper config is not a readable file")
    return model_path, config_path


def _runtime(config: RuntimeServiceConfig) -> SirahRuntime:
    return SirahRuntime(
        profile=config.profile,
        socket_path=config.socket_path,
        devices=DeviceRegistry(
            capture_devices=config.capture_devices,
            output_devices=config.output_devices,
            capture_device=config.capture_device,
            output_device=config.output_device,
        ),
        client_secrets=config.client_secrets,
        piper_model_path=config.piper_model_path,
        piper_config_path=config.piper_config_path,
        intelligence_type=config.intelligence_type,
        ollama_base_url=config.ollama_base_url,
        ollama_model=config.ollama_model,
        ollama_fallback_model=config.ollama_fallback_model,
        ollama_timeout=config.ollama_timeout,
        kokoro_url=config.kokoro_url,
        kokoro_model=config.kokoro_model,
        kokoro_voice=config.kokoro_voice,
        kokoro_speed=config.kokoro_speed,
        kokoro_timeout=config.kokoro_timeout,
        tts=config.tts,
    )


async def run_runtime(
    config: RuntimeServiceConfig,
    *,
    runtime_factory: Callable[[RuntimeServiceConfig], RuntimeLifecycle] = _runtime,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run one runtime until SIGINT or SIGTERM requests orderly shutdown."""
    runtime = runtime_factory(config)
    event = shutdown_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    signals: tuple[signal.Signals, ...] = ()
    if shutdown_event is None:
        signals = (signal.SIGINT, signal.SIGTERM)
        for signum in signals:
            loop.add_signal_handler(signum, event.set)
    started = False
    try:
        await runtime.start()
        started = True
        await event.wait()
    finally:
        if started:
            await runtime.stop()
        for signum in signals:
            loop.remove_signal_handler(signum)


async def main() -> None:
    """Load server configuration and run the sole hardware-owning process."""
    await run_runtime(RuntimeServiceConfig.from_environment(os.environ))


def cli() -> None:
    """Console-script adapter with safe configuration diagnostics."""
    try:
        asyncio.run(main())
    except RuntimeConfigurationError as error:
        print(f"sirah-runtime configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    cli()
