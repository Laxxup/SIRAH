"""Hardware adapters for SIRAH v0.3.0 (Stage 5: serial USB-UART)."""

from sirah.hardware.contract import (
    Command,
    ContractError,
    decode_payload,
    encode_command,
    format_coord,
)
from sirah.hardware.serial_adapter import SerialTransport
from sirah.hardware.transport import (
    EyeTransport,
    FramingError,
    LinkLost,
    ReadTimeout,
    TransportError,
    TransportState,
    TransportStatus,
)

__all__ = [
    "Command",
    "ContractError",
    "EyeTransport",
    "FramingError",
    "LinkLost",
    "ReadTimeout",
    "SerialTransport",
    "TransportError",
    "TransportState",
    "TransportStatus",
    "decode_payload",
    "encode_command",
    "format_coord",
]