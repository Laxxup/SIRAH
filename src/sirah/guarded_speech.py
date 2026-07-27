"""Puerta obligatoria y correlacionada para adaptadores concretos de TTS."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from .audio_turn import AudioTurnCoordinator, AudioTurnLease
from .errors import SpeechStartError
from .speech import SpeechCompletion, SpeechOutputPort, SpeechState


class HookedSpeechOutput(Protocol):
    def set_lifecycle_hooks(
        self,
        on_operation_accepted: Callable[[str], None],
        on_terminal: Callable[[str], None],
    ) -> None: ...

    @property
    def available(self) -> bool: ...
    @property
    def active(self) -> bool: ...
    @property
    def state(self) -> SpeechState: ...
    def start(self, text: str) -> str: ...
    def stop(self, expected_operation_id: str | None = None) -> bool: ...
    def poll(self) -> SpeechCompletion | None: ...
    def close(self) -> None: ...


class GuardedSpeechOutput(SpeechOutputPort):
    def __init__(
        self, driver: HookedSpeechOutput, turns: AudioTurnCoordinator
    ) -> None:
        self.__driver = driver
        self._turns = turns
        self._start_lock = threading.Lock()
        self._lock = threading.Lock()
        self._pending_start: AudioTurnLease | None = None
        self._accepted_id: str | None = None
        self._leases: dict[str, AudioTurnLease] = {}
        driver.set_lifecycle_hooks(self._on_accepted, self._on_terminal)

    @property
    def available(self) -> bool:
        return self.__driver.available

    @property
    def active(self) -> bool:
        return self.__driver.active

    @property
    def state(self) -> SpeechState:
        return self.__driver.state

    def start(self, text: str) -> str:
        with self._start_lock:
            lease = self._turns.reserve_output()
            with self._lock:
                self._pending_start = lease
                self._accepted_id = None
            try:
                returned = self.__driver.start(text)
                with self._lock:
                    accepted = self._accepted_id
                if accepted != returned:
                    raise SpeechStartError("El adaptador devolvió una correlación inválida.")
                return returned
            except Exception as error:
                with self._lock:
                    accepted = self._accepted_id
                if accepted is None:
                    self._turns.release(lease)
                else:
                    self._abort_accepted(accepted)
                if isinstance(error, SpeechStartError):
                    raise
                raise
            finally:
                with self._lock:
                    self._pending_start = None
                self._accepted_id = None

    def _abort_accepted(self, operation_id: str) -> None:
        with self._lock:
            pending = operation_id in self._leases
        if not pending:
            return
        try:
            cancelled = self.__driver.stop(operation_id)
        except Exception:
            cancelled = False
        if not cancelled:
            try:
                self.__driver.close()
            except Exception:
                pass

    def _on_accepted(self, operation_id: str) -> None:
        with self._lock:
            lease = self._pending_start
            if lease is None or self._accepted_id is not None:
                raise SpeechStartError("Handshake de salida inválido.")
            self._leases[operation_id] = lease
            self._accepted_id = operation_id

    def _on_terminal(self, operation_id: str) -> None:
        with self._lock:
            lease = self._leases.pop(operation_id, None)
        if lease is not None:
            self._turns.release(lease)

    def stop(self, expected_operation_id: str | None = None) -> bool:
        return self.__driver.stop(expected_operation_id)

    def poll(self) -> SpeechCompletion | None:
        return self.__driver.poll()

    def close(self) -> None:
        self.__driver.close()


class SpeechOutputLabControlPort(Protocol):
    def complete_active(self) -> bool: ...


class FakeSpeechOutputLabControl:
    def __init__(self, complete: Callable[[], bool]) -> None:
        self.__complete = complete

    def complete_active(self) -> bool:
        return self.__complete()
