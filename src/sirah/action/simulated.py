"""Simulated robot — deterministic fake for testing."""

from __future__ import annotations

from typing import Any

__all__ = ["SimulatedRobot"]


class SimulatedRobot:
    def __init__(self, fail_on_send: bool = False) -> None:
        self._commands: list[Any] = []
        self._fail_on_send = fail_on_send
        self._sent_count = 0

    def send(self, command: object) -> None:
        if self._fail_on_send:
            raise RuntimeError("simulated robot failure")
        self._commands.append(command)
        self._sent_count += 1

    def handled(self) -> bool:
        return self._sent_count > 0

    @property
    def commands(self) -> list[Any]:
        return self._commands

    @property
    def last_command(self) -> Any:
        return self._commands[-1] if self._commands else None

    def reset(self) -> None:
        self._commands.clear()
        self._sent_count = 0
