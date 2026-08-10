"""EyeTransport port — the single door between runtime and ESP32.

Single-authority rule (Stage 5): only the runtime opens the port. Adapters
never open on their own, never auto-reopen, and never decide policy.

All messages are payloads WITHOUT the trailing "\\n" (framing is the
adapter's concern: 63 payload bytes, max line 64 including "\\n", spec 4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class TransportState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class TransportStatus:
    state: TransportState
    detail: str = ""


class TransportError(Exception):
    """Base for transport failures (open/send/read/framing)."""


class ReadTimeout(TransportError):
    """No complete line arrived within the read timeout."""


class LinkLost(TransportError):
    """Device went away (EOF, device unplugged, port error)."""


class FramingError(TransportError):
    """Line longer than 64 bytes (spec 4) or other framing violation."""


class EyeTransport(ABC):
    """Contract port implemented by serial adapter and FakeESP32."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the link. Idempotent: no-op when already connected."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the link. Idempotent: no-op when not connected."""

    @abstractmethod
    async def send(self, payload: bytes) -> None:
        """Send one payload line (no trailing "\\n")."""

    @abstractmethod
    async def read(self, timeout: float | None = None) -> bytes | None:
        """Read one payload line or None on timeout.

        timeout=None means "use the transport default". Raises LinkLost on
        device loss, FramingError on oversized lines.
        """

    @abstractmethod
    def status(self) -> TransportStatus:
        """Current transport state (single source of truth)."""