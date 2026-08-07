"""Runtime client identity and capability access control."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from sirah.errors import RuntimeAccessDeniedError
from sirah.types import ClientCapabilities, ClientKind, RuntimeRequest

__all__ = ["RuntimeClient"]


_CLIENT_ACL: Mapping[ClientKind, frozenset[ClientCapabilities]] = {
    ClientKind.WEB_LAB: frozenset(ClientCapabilities),
    ClientKind.CLI: frozenset(ClientCapabilities),
}
_PROHIBITED_METADATA_FIELDS = frozenset({
    "capture_device", "device", "serial", "pwm", "angle", "shell", "arm",
    "path", "index", "backend", "card/device", "hw", "card",
})

RuntimeHandler = Callable[[RuntimeRequest], Awaitable[object]]


class RuntimeClient:
    """Authorised adapter that can submit a bounded runtime request."""

    def __init__(self, kind: ClientKind, runtime: RuntimeHandler) -> None:
        self._kind = kind
        self._runtime = runtime

    async def submit_text(self, text: str) -> object:
        """Submit manual text without exposing runtime-owned resources."""
        return await self.request(
            RuntimeRequest(
                capability=ClientCapabilities.CONVERSATION_SUBMIT,
                metadata={"text": text},
            )
        )

    async def read_status(self) -> object:
        """Read the runtime status snapshot."""
        return await self.request(RuntimeRequest(capability=ClientCapabilities.STATUS_READ))

    async def submit_local_voice_turn(self) -> object:
        return await self.request(
            RuntimeRequest(capability=ClientCapabilities.LOCAL_VOICE_TURN_SUBMIT)
        )

    async def request(self, request: RuntimeRequest) -> object:
        """Validate the request before it can reach the runtime boundary."""
        allowed_capabilities = _CLIENT_ACL.get(self._kind, frozenset())
        if request.capability not in allowed_capabilities:
            raise RuntimeAccessDeniedError("client capability is not authorised")
        prohibited_field = _find_prohibited_field(request.metadata)
        if prohibited_field is not None:
            raise RuntimeAccessDeniedError(
                f"runtime requests may not contain {prohibited_field!r} metadata"
            )
        return await self._runtime(request)


def _find_prohibited_field(value: object) -> str | None:
    if isinstance(value, str):
        if value.strip().lower() in _PROHIBITED_METADATA_FIELDS:
            return value
    elif isinstance(value, Mapping):
        for field, nested_value in value.items():
            lowered = field.strip().lower()
            if lowered in _PROHIBITED_METADATA_FIELDS or lowered.startswith("hw:"):
                return field
            prohibited_field = _find_prohibited_field(nested_value)
            if prohibited_field is not None:
                return prohibited_field
    elif isinstance(value, tuple | frozenset):
        for nested_value in value:
            prohibited_field = _find_prohibited_field(nested_value)
            if prohibited_field is not None:
                return prohibited_field
    return None
