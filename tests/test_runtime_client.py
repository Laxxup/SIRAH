"""Runtime client ACL contract tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from sirah.core.devices import DeviceRegistry
from sirah.core.runtime import SirahRuntime
from sirah.core.runtime_client import RuntimeClient
from sirah.core.runtime_transport import RuntimeTransport, RuntimeTransportClient
from sirah.errors import (
    DeviceNotAllowedError,
    RuntimeAccessDeniedError,
    RuntimeAssemblyAccessError,
)
from sirah.factory import SystemAssembly, SystemProfile, build_system
from sirah.types import ClientCapabilities, ClientKind, RuntimeRequest
from sirah.voice.audio_service import AudioTurnService


class RecordingRuntime:
    """Deterministic runtime boundary used to observe dispatched requests."""

    def __init__(self) -> None:
        self.requests: list[RuntimeRequest] = []

    async def __call__(self, request: RuntimeRequest) -> object:
        self.requests.append(request)
        return {"capability": request.capability.value}


@pytest.mark.asyncio
@pytest.mark.parametrize("client_kind", [ClientKind.WEB_LAB, ClientKind.CLI])
async def test_web_lab_and_cli_submit_text_and_read_status(
    client_kind: ClientKind,
) -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(client_kind, runtime)

    submitted = await client.submit_text("hola")
    status = await client.read_status()

    assert submitted == {"capability": "conversation.submit"}
    assert status == {"capability": "status.read"}
    assert [request.capability for request in runtime.requests] == [
        ClientCapabilities.CONVERSATION_SUBMIT,
        ClientCapabilities.STATUS_READ,
    ]
    assert runtime.requests[0].metadata == {"text": "hola"}


def test_runtime_request_metadata_is_immutable() -> None:
    request = RuntimeRequest(
        capability=ClientCapabilities.STATUS_READ,
        metadata={"filters": {"component": "voice"}},
    )

    with pytest.raises(TypeError):
        request.metadata["extra"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.metadata["filters"]["component"] = "action"  # type: ignore[index]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prohibited_field",
    ["capture_device", "device", "hw", "card", "hw:0,0", "card/device", "path", "index", "backend"],
)
async def test_prohibited_request_fields_are_rejected_before_runtime_dispatch(
    prohibited_field: str,
) -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(ClientKind.WEB_LAB, runtime)
    request = RuntimeRequest(
        capability=ClientCapabilities.CONVERSATION_SUBMIT,
        metadata={"text": "hola", prohibited_field: "forbidden"},
    )

    with pytest.raises(RuntimeAccessDeniedError, match=prohibited_field):
        await client.request(request)

    assert runtime.requests == []


@pytest.mark.asyncio
async def test_normalized_nested_hardware_alias_is_rejected_before_runtime_dispatch() -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(ClientKind.WEB_LAB, runtime)
    request = RuntimeRequest(
        capability=ClientCapabilities.LOCAL_VOICE_TURN_SUBMIT,
        metadata={"payload": {" Card ": "card-0", " HW ": "hw:0,0"}},
    )

    with pytest.raises(RuntimeAccessDeniedError, match="Card|HW"):
        await client.request(request)

    assert runtime.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", [" hw ", " card "])
async def test_nested_whitespace_padded_hardware_alias_value_is_rejected(
    alias: str,
) -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(ClientKind.WEB_LAB, runtime)
    request = RuntimeRequest(
        capability=ClientCapabilities.LOCAL_VOICE_TURN_SUBMIT,
        metadata={"payload": {"selection": alias}},
    )

    with pytest.raises(RuntimeAccessDeniedError, match=alias.strip()):
        await client.request(request)

    assert runtime.requests == []


@pytest.mark.asyncio
async def test_prohibited_field_in_nested_sequence_is_rejected_before_runtime_dispatch() -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(ClientKind.WEB_LAB, runtime)
    request = RuntimeRequest(
        capability=ClientCapabilities.CONVERSATION_SUBMIT,
        metadata={"payload": [{"device": "motor-1"}]},
    )

    with pytest.raises(RuntimeAccessDeniedError, match="device"):
        await client.request(request)

    assert runtime.requests == []


@pytest.mark.asyncio
async def test_prohibited_field_in_nested_frozenset_is_rejected_before_runtime_dispatch() -> None:
    runtime = RecordingRuntime()
    client = RuntimeClient(ClientKind.WEB_LAB, runtime)
    request = RuntimeRequest(
        capability=ClientCapabilities.CONVERSATION_SUBMIT,
        metadata={"payload": frozenset({"device"})},
    )

    with pytest.raises(RuntimeAccessDeniedError, match="device"):
        await client.request(request)

    assert runtime.requests == []


def test_only_initial_client_capabilities_are_exposed() -> None:
    assert {capability.value for capability in ClientCapabilities} == {
        "conversation.submit",
        "status.read",
        "diagnostics.read",
        "laboratory.manual_text",
        "local_voice_turn.submit",
    }


@pytest.mark.asyncio
async def test_runtime_builds_one_disarmed_assembly(monkeypatch: pytest.MonkeyPatch) -> None:
    import sirah.core.runtime as runtime_module

    original_build_system = runtime_module.build_system
    assemblies = 0

    def build_once(*args: object, **kwargs: object) -> object:
        nonlocal assemblies
        assemblies += 1
        return original_build_system(*args, **kwargs)

    monkeypatch.setattr(runtime_module, "build_system", build_once)
    runtime = SirahRuntime(client_secrets={ClientKind.CLI: "cli-secret"})

    await runtime.start()
    try:
        assert assemblies == 1
        assert runtime.hardware_armed is False
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_unix_socket_client_disconnect_does_not_stop_runtime(tmp_path) -> None:
    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
    )

    await runtime.start()
    try:
        reader, writer = await __import__("asyncio").open_unix_connection(socket_path)
        del reader
        writer.close()
        await writer.wait_closed()

        assert runtime.is_running is True
        client = RuntimeClient(
            ClientKind.CLI,
            RuntimeTransportClient(socket_path, ClientKind.CLI, "cli-secret"),
        )
        status = await client.read_status()
        assert status["components"]
    finally:
        await runtime.stop()


@pytest.mark.parametrize(
    ("capture_devices", "output_devices", "method", "device"),
    [
        (("mic-primary",), ("speaker-primary",), "capture", "mic-unknown"),
        (("mic-primary",), ("speaker-primary",), "output", "speaker-unknown"),
    ],
)
def test_device_registry_rejects_unknown_configured_device(
    capture_devices: tuple[str, ...],
    output_devices: tuple[str, ...],
    method: str,
    device: str,
) -> None:
    registry = DeviceRegistry(
        capture_devices=capture_devices,
        output_devices=output_devices,
    )

    with pytest.raises(DeviceNotAllowedError):
        getattr(registry, method)(device)


def test_device_registry_retains_server_selected_output_device() -> None:
    registry = DeviceRegistry(
        capture_devices=("mic-primary",),
        output_devices=("speaker-primary", "speaker-backup"),
        output_device="speaker-backup",
    )

    assert registry.configured_output_device == "speaker-backup"


def test_factory_rejects_direct_assembly_outside_runtime() -> None:
    with pytest.raises(RuntimeAssemblyAccessError):
        build_system(profile=SystemProfile.DEV_LAPTOP)


@pytest.mark.asyncio
async def test_runtime_reuses_rolled_back_assembly_after_start_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import sirah.core.runtime as runtime_module

    assemblies = 0
    original_build_system = runtime_module.build_system

    def count_assembly(*args: object, **kwargs: object) -> object:
        nonlocal assemblies
        assemblies += 1
        return original_build_system(*args, **kwargs)

    async def fail_start(*args: object) -> None:
        raise OSError("socket unavailable")

    monkeypatch.setattr(runtime_module, "build_system", count_assembly)
    runtime = SirahRuntime(
        socket_path=tmp_path / "sirah.sock",
        client_secrets={ClientKind.CLI: "cli-secret"},
    )
    monkeypatch.setattr(runtime._transport, "start", fail_start)

    with pytest.raises(OSError, match="socket unavailable"):
        await runtime.start()

    assert assemblies == 1
    assert runtime.is_running is False
    assert runtime._assembly is not None
    assert runtime._assembly.orchestrator.is_running is False

    monkeypatch.undo()
    await runtime.start()
    try:
        assert assemblies == 1
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_socket_rejects_untrusted_client_identity(tmp_path) -> None:
    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
    )

    await runtime.start()
    try:
        client = RuntimeClient(
            ClientKind.CLI,
            RuntimeTransportClient(socket_path, ClientKind.CLI, "wrong-secret"),
        )
        with pytest.raises(RuntimeError, match="unauthorised"):
            await client.read_status()
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_socket_rejects_connection_over_limit(tmp_path) -> None:
    import asyncio

    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
        max_connections=1,
    )

    await runtime.start()
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        client = RuntimeClient(
            ClientKind.CLI,
            RuntimeTransportClient(socket_path, ClientKind.CLI, "cli-secret"),
        )
        with pytest.raises(RuntimeError, match="connection limit"):
            await client.read_status()
    finally:
        writer.close()
        await writer.wait_closed()
        del reader
        await runtime.stop()


@pytest.mark.asyncio
async def test_socket_rejects_request_exceeding_configured_size(tmp_path) -> None:
    import asyncio

    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
        max_request_bytes=32,
    )

    await runtime.start()
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        writer.write(b"x" * 33 + b"\n")
        await writer.drain()
        assert b"request limit" in await reader.readline()
        writer.close()
        await writer.wait_closed()
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_socket_rejects_request_exceeding_configured_read_timeout(tmp_path) -> None:
    import asyncio

    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
        request_timeout_s=0.01,
    )

    await runtime.start()
    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)
        assert b"request timed out" in await reader.readline()
        writer.close()
        await writer.wait_closed()
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_transport_client_times_out_waiting_for_response(tmp_path) -> None:
    import asyncio

    socket_path = tmp_path / "sirah.sock"

    async def no_response(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.read()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(no_response, path=socket_path)
    client = RuntimeTransportClient(
        socket_path,
        ClientKind.CLI,
        "cli-secret",
        response_timeout_s=0.01,
    )
    try:
        with pytest.raises(RuntimeError, match="response timed out"):
            await client(RuntimeRequest(capability=ClientCapabilities.STATUS_READ))
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_transport_client_rejects_response_exceeding_configured_size(tmp_path) -> None:
    import asyncio

    socket_path = tmp_path / "sirah.sock"

    async def overlong_response(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.readline()
        writer.write(b"x" * 33 + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(overlong_response, path=socket_path)
    client = RuntimeTransportClient(
        socket_path,
        ClientKind.CLI,
        "cli-secret",
        max_response_bytes=32,
    )
    try:
        with pytest.raises(RuntimeError, match="response limit"):
            await client(RuntimeRequest(capability=ClientCapabilities.STATUS_READ))
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_runtime_rejects_start_when_socket_endpoint_is_active(tmp_path) -> None:
    socket_path = tmp_path / "sirah.sock"
    first = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
    )
    second = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
    )

    await first.start()
    try:
        with pytest.raises(OSError, match="already active"):
            await second.start()
        client = RuntimeClient(
            ClientKind.CLI,
            RuntimeTransportClient(socket_path, ClientKind.CLI, "cli-secret"),
        )
        assert (await client.read_status())["components"]
    finally:
        await second.stop()
        await first.stop()


@pytest.mark.asyncio
async def test_transport_stop_does_not_unlink_socket_it_does_not_own(tmp_path) -> None:
    socket_path = tmp_path / "sirah.sock"
    runtime = SirahRuntime(
        socket_path=socket_path,
        client_secrets={ClientKind.CLI: "cli-secret"},
    )
    other_transport = RuntimeTransport(
        socket_path,
        client_secrets={ClientKind.CLI: "other-secret"},
        max_connections=1,
        max_request_bytes=128,
        request_timeout_s=1.0,
    )

    await runtime.start()
    try:
        await other_transport.stop()
        client = RuntimeClient(
            ClientKind.CLI,
            RuntimeTransportClient(socket_path, ClientKind.CLI, "cli-secret"),
        )
        assert (await client.read_status())["components"]
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_runtime_stop_attempts_every_cleanup_and_clears_running_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Stopper:
        def __init__(self, name: str, fails: bool = False) -> None:
            self._name = name
            self._fails = fails

        async def stop(self) -> None:
            events.append(self._name)
            if self._fails:
                raise RuntimeError(f"{self._name} stop failed")

    runtime = SirahRuntime(client_secrets={ClientKind.CLI: "cli-secret"})
    transport = Stopper("transport", fails=True)
    runtime._running = True
    runtime._audio = cast(AudioTurnService, Stopper("audio", fails=True))
    runtime._assembly = cast(
        SystemAssembly,
        SimpleNamespace(orchestrator=Stopper("orchestrator", fails=True)),
    )
    monkeypatch.setattr(runtime._transport, "stop", transport.stop)

    with pytest.raises(RuntimeError, match="transport stop failed"):
        await runtime.stop()

    assert events == ["transport", "audio", "orchestrator"]
    assert runtime.is_running is False
    assert runtime._audio is None
    assert runtime._assembly is None
