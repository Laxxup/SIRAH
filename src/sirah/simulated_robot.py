"""Adaptador RobotPort determinista para la composición local de SIRAH."""

from enum import Enum

from sirah_cortex import (
    Event,
    EventType,
    RobotCommand,
    RobotUnavailableError,
)


class SimulatedFailure(str, Enum):
    """Fallo que se aplicará al siguiente envío."""

    NONE = "none"
    REJECT = "reject"
    UNAVAILABLE = "unavailable"


class SimulatedRobotAdapter:
    """RobotPort sin red ni hardware, observable por comandos y eventos."""

    def __init__(self) -> None:
        self._connected = False
        self._events: list[Event] = []
        self.commands: list[RobotCommand] = []
        self.next_failure = SimulatedFailure.NONE

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if not self._connected:
            self._connected = True
            self._events.append(Event(EventType.ROBOT_CONNECTED))

    def send(self, command: RobotCommand) -> None:
        if not self._connected or self.next_failure is SimulatedFailure.UNAVAILABLE:
            self.next_failure = SimulatedFailure.NONE
            raise RobotUnavailableError("El adaptador simulado no está disponible.")
        if self.next_failure is SimulatedFailure.REJECT:
            self.next_failure = SimulatedFailure.NONE
            self._events.append(
                Event(
                    EventType.COMMAND_FAILED,
                    {"command_id": command.command_id, "reason": "simulated_reject"},
                )
            )
            raise RobotUnavailableError("El adaptador simulado rechazó el comando.")
        self.commands.append(command)
        payload = {"command_id": command.command_id}
        self._events.extend(
            [
                Event(EventType.COMMAND_ACCEPTED, payload),
                Event(EventType.COMMAND_COMPLETED, payload),
            ]
        )

    def read_events(self) -> list[Event]:
        events = self._events[:]
        self._events.clear()
        return events

    def emergency_stop(self) -> None:
        self._events.append(Event(EventType.EMERGENCY_STOP))

    def close(self) -> None:
        if self._connected:
            self._connected = False
            self._events.append(Event(EventType.ROBOT_DISCONNECTED))

