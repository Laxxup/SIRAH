"""Headless runtime supervisor and sole system assembly owner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from sirah.core.devices import DeviceRegistry
from sirah.core.runtime_client import RuntimeClient
from sirah.core.runtime_transport import RuntimeTransport
from sirah.errors import SpeechError
from sirah.factory import (
    _RUNTIME_ASSEMBLY_TOKEN,
    SystemAssembly,
    SystemProfile,
    build_system,
)
from sirah.types import (
    ClientKind,
    ComponentId,
    ComponentKind,
    ComponentStatus,
    RuntimeRequest,
    SystemSnapshot,
)
from sirah.voice.audio_service import AudioTurnService, CapturePort
from sirah.voice.coordinator import AudioTurnCoordinator
from sirah.voice.mic_capture import MicCapture

__all__ = ["SirahRuntime"]


class SirahRuntime:
    """Own the assembled system and expose bounded client operations."""

    def __init__(
        self,
        profile: SystemProfile = SystemProfile.DEV_LAPTOP,
        socket_path: Path = Path("/tmp/sirah-runtime.sock"),
        devices: DeviceRegistry | None = None,
        client_secrets: Mapping[ClientKind, str] | None = None,
        max_connections: int = 16,
        max_request_bytes: int = 16_384,
        request_timeout_s: float = 5.0,
        capture_factory: Callable[[str], CapturePort] = MicCapture,
        piper_model_path: Path | None = None,
        piper_config_path: Path | None = None,
    ) -> None:
        if not client_secrets:
            raise ValueError("runtime client secrets must be configured")
        self._profile = profile
        self._devices = devices or DeviceRegistry()
        self._capture_device = self._devices.configured_capture_device
        self._capture_factory = capture_factory
        self._transport = RuntimeTransport(
            socket_path,
            client_secrets=client_secrets,
            max_connections=max_connections,
            max_request_bytes=max_request_bytes,
            request_timeout_s=request_timeout_s,
        )
        self._assembly: SystemAssembly | None = None
        self._running = False
        self._hardware_armed = False
        self._audio: AudioTurnService | None = None
        self._piper_model_path = piper_model_path
        self._piper_config_path = piper_config_path

    @property
    def hardware_armed(self) -> bool:
        """Hardware control is intentionally unavailable in this phase."""
        return self._hardware_armed

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        if self._assembly is None:
            self._assembly = build_system(
                profile=self._profile,
                stt="whisper",
                tts="piper" if self._piper_model_path is not None else "fake",
                piper_model_path=(str(self._piper_model_path) if self._piper_model_path else None),
                piper_config_path=(str(self._piper_config_path) if self._piper_config_path else None),
                output_device=self._devices.configured_output_device,
                _runtime_token=_RUNTIME_ASSEMBLY_TOKEN,
            )
        if self._audio is None:
            self._audio = AudioTurnService(
                capture_device=self._capture_device,
                capture_factory=self._capture_factory,
                recognizer=self._assembly.speech_input,
                speech_output=self._assembly.speech_output,
                coordinator=AudioTurnCoordinator(),
                respond=self._respond_to_voice,
            )
            self._assembly.orchestrator.set_voice_service(self._audio)
            if self._assembly.situational is not None:
                self._assembly.situational.set_voice_service(self._audio)
        try:
            await self._assembly.orchestrator.start()
            if self._piper_model_path is not None:
                try:
                    await self._assembly.speech_output.start()  # type: ignore[union-attr]
                except SpeechError:
                    self._assembly.registry.update(
                        ComponentId(ComponentKind.VOICE, "speech"),
                        ComponentStatus.DEGRADED,
                        "Piper unavailable",
                    )
            await self._audio.start()
            if not await self._audio.recognizer_healthy():
                self._assembly.registry.update(
                    ComponentId(ComponentKind.VOICE, "speech"),
                    ComponentStatus.DEGRADED,
                    "speech recognizer unavailable",
                )
            await self._transport.start(self._serve_request)
        except BaseException:
            await self._transport.stop()
            await self._audio.stop()
            if self._piper_model_path is not None:
                await self._assembly.speech_output.stop()  # type: ignore[union-attr]
            await self._assembly.orchestrator.stop()
            raise
        self._running = True

    async def stop(self) -> None:
        if not self._running:
            return
        failure: BaseException | None = None
        cleanup = [self._transport.stop]
        if self._audio is not None:
            cleanup.append(self._audio.stop)
        assert self._assembly is not None
        if self._piper_model_path is not None:
            cleanup.append(self._assembly.speech_output.stop)  # type: ignore[union-attr]
        cleanup.append(self._assembly.orchestrator.stop)
        try:
            for stop in cleanup:
                try:
                    await stop()
                except BaseException as error:
                    if failure is None:
                        failure = error
        finally:
            self._running = False
            self._audio = None
            self._assembly = None
        if failure is not None:
            raise failure

    async def submit_text(self, text: str) -> object:
        """Submit text through the runtime-owned orchestrator."""
        return await self._orchestrator.handle_text(text)

    async def submit_local_voice_turn(self) -> object:
        """Run one runtime-owned local audio turn."""
        if self._audio is None:
            raise RuntimeError("runtime is not started")
        return await self._audio.submit_human_turn()

    async def _respond_to_voice(self, transcript: str) -> str:
        return (await self._orchestrator.handle_text(transcript)).message.content

    def snapshot(self) -> SystemSnapshot:
        """Return the runtime's immutable component snapshot."""
        return self._orchestrator.snapshot

    async def _serve_request(
        self, kind: ClientKind, request: RuntimeRequest
    ) -> object:
        client = RuntimeClient(kind, self._dispatch_request)
        return await client.request(request)

    async def _dispatch_request(self, request: RuntimeRequest) -> object:
        if request.capability.value in {
            "conversation.submit",
            "laboratory.manual_text",
        }:
            text = request.metadata.get("text")
            if not isinstance(text, str):
                raise ValueError("text request requires text metadata")
            return await self.submit_text(text)
        if request.capability.value == "local_voice_turn.submit":
            return await self.submit_local_voice_turn()
        if request.capability.value in {"status.read", "diagnostics.read"}:
            return self.snapshot()
        raise ValueError("unsupported runtime capability")

    @property
    def _orchestrator(self):
        if self._assembly is None:
            raise RuntimeError("runtime is not started")
        return self._assembly.orchestrator
