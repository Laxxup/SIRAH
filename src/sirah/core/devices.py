"""Runtime-owned capture and output device allowlists."""

from __future__ import annotations

from collections.abc import Iterable

from sirah.errors import DeviceNotAllowedError

__all__ = ["DeviceRegistry"]


class DeviceRegistry:
    """Validate internal device selection against configured inventory."""

    def __init__(
        self,
        capture_devices: Iterable[str] = ("default",),
        output_devices: Iterable[str] = (),
        capture_device: str | None = None,
        output_device: str | None = None,
    ) -> None:
        configured_capture = tuple(capture_devices)
        configured_output = tuple(output_devices)
        self._capture_devices = frozenset(configured_capture)
        self._output_devices = frozenset(configured_output)
        selected_capture = capture_device or (
            configured_capture[0] if configured_capture else "default"
        )
        self._capture_device = self.capture(selected_capture)
        selected_output = output_device or (
            configured_output[0] if configured_output else None
        )
        self._output_device = (
            self.output(selected_output) if selected_output is not None else None
        )

    @property
    def configured_capture_device(self) -> str:
        """Return the sole capture device chosen by server configuration."""
        return self._capture_device

    @property
    def configured_output_device(self) -> str | None:
        """Return the server-selected output device for a future runtime owner."""
        return self._output_device

    def capture(self, device: str) -> str:
        """Return an allowed capture device identifier."""
        return self._allowed(device, self._capture_devices, "capture")

    def output(self, device: str) -> str:
        """Return an allowed output device identifier."""
        return self._allowed(device, self._output_devices, "output")

    @staticmethod
    def _allowed(device: str, allowed: frozenset[str], kind: str) -> str:
        if device not in allowed:
            raise DeviceNotAllowedError(f"unknown {kind} device")
        return device
