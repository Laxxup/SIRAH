"""Unix domain socket transport for bounded runtime requests."""

from __future__ import annotations

import asyncio
import hmac
import json
import socket
import stat
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

from sirah.errors import RuntimeAccessDeniedError, SirahError
from sirah.types import ClientCapabilities, ClientKind, RuntimeRequest

__all__ = ["RuntimeTransport", "RuntimeTransportClient"]

RuntimeHandler = Callable[[ClientKind, RuntimeRequest], Awaitable[object]]


class RuntimeTransport:
    """Serve runtime requests without giving clients runtime object access."""

    def __init__(
        self,
        socket_path: Path,
        *,
        client_secrets: Mapping[ClientKind, str],
        max_connections: int,
        max_request_bytes: int,
        request_timeout_s: float,
    ) -> None:
        if max_connections < 1 or max_request_bytes < 1 or request_timeout_s <= 0:
            raise ValueError("runtime transport limits must be positive")
        self._socket_path = socket_path
        self._client_secrets = dict(client_secrets)
        self._max_connections = max_connections
        self._max_request_bytes = max_request_bytes
        self._request_timeout_s = request_timeout_s
        self._server: asyncio.AbstractServer | None = None
        self._handler: RuntimeHandler | None = None
        self._active_connections = 0
        self._socket_identity: tuple[int, int] | None = None

    async def start(self, handler: RuntimeHandler) -> None:
        if self._server is not None:
            return
        if self._socket_path.exists():
            socket_stat = self._socket_path.stat()
            if not stat.S_ISSOCK(socket_stat.st_mode):
                raise FileExistsError("runtime socket path is not a socket")
            if _socket_is_active(self._socket_path):
                raise OSError("runtime socket endpoint is already active")
            self._socket_path.unlink()
        self._handler = handler
        self._server = await asyncio.start_unix_server(
            self,
            path=self._socket_path,
            limit=self._max_request_bytes + 1,
        )
        socket_stat = self._socket_path.stat()
        self._socket_identity = (socket_stat.st_dev, socket_stat.st_ino)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._handler = None
        if self._owns_socket_path():
            self._socket_path.unlink()
        self._socket_identity = None

    def _owns_socket_path(self) -> bool:
        if self._socket_identity is None:
            return False
        try:
            socket_stat = self._socket_path.stat()
        except FileNotFoundError:
            return False
        return self._socket_identity == (socket_stat.st_dev, socket_stat.st_ino)

    async def __call__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self._active_connections >= self._max_connections:
            await self._write_error(writer, "connection limit exceeded")
            writer.close()
            await writer.wait_closed()
            return
        self._active_connections += 1
        try:
            line = await asyncio.wait_for(
                reader.readuntil(b"\n"), timeout=self._request_timeout_s
            )
            if not line:
                return
            if len(line) > self._max_request_bytes:
                raise ValueError("request limit exceeded")
            request_data = json.loads(line)
            if not isinstance(request_data, dict):
                raise ValueError("request must be an object")
            kind = ClientKind(request_data["kind"])
            self._authenticate(kind, request_data.get("secret"))
            request = RuntimeRequest(
                capability=ClientCapabilities(request_data["capability"]),
                metadata=request_data.get("metadata", {}),
            )
            if self._handler is None:
                raise RuntimeError("runtime transport is not started")
            result = await asyncio.wait_for(
                self._handler(kind, request), timeout=self._request_timeout_s
            )
            writer.write(_encode({"result": result}) + b"\n")
            await writer.drain()
        except asyncio.LimitOverrunError:
            await self._write_error(writer, "request limit exceeded")
        except asyncio.IncompleteReadError:
            pass
        except TimeoutError:
            await self._write_error(writer, "request timed out")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, SirahError) as exc:
            await self._write_error(writer, str(exc))
        finally:
            self._active_connections -= 1
            writer.close()
            await writer.wait_closed()

    def _authenticate(self, kind: ClientKind, secret: object) -> None:
        configured_secret = self._client_secrets.get(kind)
        if not isinstance(secret, str) or configured_secret is None:
            raise RuntimeAccessDeniedError("unauthorised runtime client")
        if not hmac.compare_digest(secret, configured_secret):
            raise RuntimeAccessDeniedError("unauthorised runtime client")

    @staticmethod
    async def _write_error(writer: asyncio.StreamWriter, error: str) -> None:
        writer.write(_encode({"error": error}) + b"\n")
        await writer.drain()

class RuntimeTransportClient:
    """Request adapter passed to ``RuntimeClient`` by external clients."""

    def __init__(
        self,
        socket_path: Path,
        kind: ClientKind,
        secret: str,
        *,
        response_timeout_s: float = 5.0,
        max_response_bytes: int = 16_384,
    ) -> None:
        if response_timeout_s <= 0 or max_response_bytes < 1:
            raise ValueError("runtime client limits must be positive")
        self._socket_path = socket_path
        self._kind = kind
        self._secret = secret
        self._response_timeout_s = response_timeout_s
        self._max_response_bytes = max_response_bytes

    async def __call__(self, request: RuntimeRequest) -> object:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(
                self._socket_path,
                limit=self._max_response_bytes + 1,
            ),
            timeout=self._response_timeout_s,
        )
        try:
            payload = {
                "kind": self._kind.value,
                "secret": self._secret,
                "capability": request.capability.value,
                "metadata": request.metadata,
            }
            writer.write(_encode(payload) + b"\n")
            await writer.drain()
            try:
                line = await asyncio.wait_for(
                    reader.readuntil(b"\n"), timeout=self._response_timeout_s
                )
            except asyncio.LimitOverrunError as exc:
                raise RuntimeError("response limit exceeded") from exc
            except asyncio.IncompleteReadError as exc:
                raise RuntimeError("runtime closed response") from exc
            except TimeoutError as exc:
                raise RuntimeError("response timed out") from exc
            if len(line) > self._max_response_bytes:
                raise RuntimeError("response limit exceeded")
            response = json.loads(line)
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]
        finally:
            writer.close()
            await writer.wait_closed()


def _encode(value: object) -> bytes:
    return json.dumps(value, default=_json_default, separators=(",", ":")).encode()


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def _socket_is_active(socket_path: Path) -> bool:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.1)
        try:
            probe.connect(str(socket_path))
        except ConnectionRefusedError:
            return False
        except FileNotFoundError:
            return False
        return True
