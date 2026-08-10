"""Hardware adapters for SIRAH v0.3.0 (Stage 5: serial USB-UART)."""

from sirah.hardware.contract import (
    Command,
    ContractError,
    decode_payload,
    encode_command,
    format_coord,
)
from sirah.hardware.fake_esp32 import BlinkConfig, BlinkFSM, FakeESP32, GazeEaser
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
    "BlinkConfig",
    "BlinkFSM",
    "Command",
    "ContractError",
    "EyeTransport",
    "FakeESP32",
    "FramingError",
    "GazeEaser",
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