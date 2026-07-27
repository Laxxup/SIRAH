"""Contratos y runtime acotado de entrada de voz local."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable
from typing import Protocol

from .audio_turn import AudioTurnCoordinator, AudioTurnLease
from .errors import SpeechBusyError, SpeechInputError, SpeechUnavailableError


class PcmReadKind(str, Enum):
    DATA = "data"
    TIMEOUT = "timeout"
    EOF = "eof"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PcmReadResult:
    kind: PcmReadKind
    data: bytes = b""
    safe_reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind is PcmReadKind.DATA:
            if len(self.data) < 2 or len(self.data) % 2:
                raise ValueError("PCM DATA debe contener muestras S16_LE completas.")
        elif self.data:
            raise ValueError("Solo DATA puede contener PCM.")


class PcmCapturePort(Protocol):
    @property
    def available(self) -> bool: ...
    @property
    def active(self) -> bool: ...
    @property
    def safe_reason(self) -> str | None: ...
    def start(self) -> None: ...
    def read_chunk(self) -> PcmReadResult: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class RecognitionUpdateKind(str, Enum):
    PARTIAL = "partial"
    FINAL = "final"
    NO_SPEECH = "no_speech"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class RecognitionUpdate:
    kind: RecognitionUpdateKind
    text: str | None = None
    confidence: float | None = None
    safe_reason: str | None = None


class SpeechRecognizerPort(Protocol):
    @property
    def available(self) -> bool: ...
    def reset(self) -> None: ...
    def accept_pcm(self, chunk: bytes) -> RecognitionUpdate | None: ...
    def finalize(self) -> RecognitionUpdate: ...
    def close(self) -> None: ...


class SpeechInputState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    FINALIZING = "finalizing"
    CANCELLING = "cancelling"
    CLOSED = "closed"


class SpeechRecognitionEventKind(str, Enum):
    PARTIAL = "partial"
    FINAL = "final"
    NO_SPEECH = "no_speech"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class SpeechRecognitionEvent:
    operation_id: str
    kind: SpeechRecognitionEventKind
    text: str | None = None
    confidence: float | None = None
    safe_reason: str | None = None


@dataclass(slots=True)
class _Operation:
    operation_id: str
    lease: AudioTurnLease
    returned: bool = False
    terminal: bool = False
    cause: SpeechRecognitionEventKind | None = None


class SpeechInputRuntime:
    """Un worker; parciales coalescidos y una transición terminal."""

    def __init__(
        self,
        capture: PcmCapturePort,
        recognizer: SpeechRecognizerPort,
        turns: AudioTurnCoordinator,
        *,
        inactivity_timeout_seconds: float = 5.0,
        maximum_duration_seconds: float = 30.0,
        max_partial_chars: int = 256,
        close_join_timeout_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if inactivity_timeout_seconds <= 0 or maximum_duration_seconds <= 0:
            raise ValueError("Los deadlines deben ser positivos.")
        if max_partial_chars <= 0 or close_join_timeout_seconds <= 0:
            raise ValueError("max_partial_chars debe ser positivo.")
        self._capture, self._recognizer, self._turns = capture, recognizer, turns
        self._inactivity = inactivity_timeout_seconds
        self._maximum = maximum_duration_seconds
        self._max_partial = max_partial_chars
        self._close_join_timeout = close_join_timeout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._finalize = threading.Event()
        self._state = SpeechInputState.IDLE
        self._operation: _Operation | None = None
        self._partial: SpeechRecognitionEvent | None = None
        self._terminal: SpeechRecognitionEvent | None = None
        self._worker: threading.Thread | None = None

    @property
    def available(self) -> bool:
        return (
            self._capture.available
            and self._recognizer.available
            and self.state is not SpeechInputState.CLOSED
        )

    @property
    def active(self) -> bool:
        with self._lock:
            return self._operation is not None and not self._operation.terminal

    @property
    def state(self) -> SpeechInputState:
        with self._lock:
            return self._state

    def start(self) -> str:
        lease = self._turns.reserve_input()
        operation: _Operation | None = None
        try:
            available = self._capture.available and self._recognizer.available
            with self._lock:
                if self._state is SpeechInputState.CLOSED or not available:
                    raise SpeechUnavailableError("Entrada de voz no disponible.")
                if self._operation is not None or self._terminal is not None:
                    raise SpeechBusyError("Entrada de voz ocupada.")
                operation = _Operation(f"stt-{uuid.uuid4().hex}", lease)
                self._operation = operation
                self._state = SpeechInputState.LISTENING
                self._cancel.clear()
                self._finalize.clear()
                worker = threading.Thread(
                    target=self._run,
                    args=(operation.operation_id,),
                    name="sirah-speech-input",
                    daemon=False,
                )
                self._worker = worker
            worker.start()
            operation.returned = True
            return operation.operation_id
        except Exception as error:
            with self._lock:
                if self._operation is operation:
                    self._operation = None
                    self._worker = None
                    if self._state is not SpeechInputState.CLOSED:
                        self._state = SpeechInputState.IDLE
            self._turns.release(lease)
            if isinstance(error, (SpeechBusyError, SpeechUnavailableError)):
                raise
            raise SpeechInputError("speech_input_start_failed") from error

    def finalize(self, expected_operation_id: str | None = None) -> bool:
        return self._request(expected_operation_id, final=True)

    def cancel(self, expected_operation_id: str | None = None) -> bool:
        return self._request(expected_operation_id, final=False)

    def _request(self, expected: str | None, *, final: bool) -> bool:
        with self._lock:
            operation = self._operation
            if (
                operation is None
                or operation.terminal
                or (expected is not None and expected != operation.operation_id)
            ):
                return False
            cause = (
                SpeechRecognitionEventKind.FINAL
                if final
                else SpeechRecognitionEventKind.CANCELLED
            )
            if operation.cause is not None:
                return operation.cause is cause
            operation.cause = cause
            self._state = (
                SpeechInputState.FINALIZING
                if final
                else SpeechInputState.CANCELLING
            )
            (self._finalize if final else self._cancel).set()
        return True

    def poll(self) -> SpeechRecognitionEvent | None:
        with self._lock:
            if self._terminal is not None:
                event, self._terminal = self._terminal, None
                self._operation = None
                return event
            partial = self._partial
            self._partial = None
            return partial

    def close(self) -> None:
        with self._lock:
            if self._state is SpeechInputState.CLOSED:
                return
            operation = self._operation
        if operation is not None and not operation.terminal:
            self.cancel(operation.operation_id)
        with self._lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(self._close_join_timeout)
        if worker is None or not worker.is_alive():
            try:
                self._capture.close()
            except Exception:
                pass
            try:
                self._recognizer.close()
            except Exception:
                pass
        with self._lock:
            self._state = SpeechInputState.CLOSED

    def _run(self, operation_id: str) -> None:
        started = self._clock()
        last_data = started
        terminal: tuple[SpeechRecognitionEventKind, str | None, str | None] | None = None
        try:
            if self._requested_cause(operation_id) is SpeechRecognitionEventKind.CANCELLED:
                terminal = (SpeechRecognitionEventKind.CANCELLED, None, "cancelled")
                return
            self._capture.start()
            if self._requested_cause(operation_id) is SpeechRecognitionEventKind.CANCELLED:
                terminal = (SpeechRecognitionEventKind.CANCELLED, None, "cancelled")
                return
            self._recognizer.reset()
            while terminal is None:
                requested = self._requested_cause(operation_id)
                if requested is SpeechRecognitionEventKind.CANCELLED:
                    terminal = (SpeechRecognitionEventKind.CANCELLED, None, "cancelled")
                    break
                if requested is SpeechRecognitionEventKind.FINAL:
                    update = self._recognizer.finalize()
                    terminal = self._map_final(update)
                    break
                now = self._clock()
                if now - started >= self._maximum:
                    if self._claim_cause(
                        operation_id, SpeechRecognitionEventKind.TIMEOUT
                    ):
                        terminal = (
                            SpeechRecognitionEventKind.TIMEOUT,
                            None,
                            "maximum_duration",
                        )
                    break
                if self._requested_cause(operation_id) is not None:
                    continue
                result = self._capture.read_chunk()
                requested = self._requested_cause(operation_id)
                if requested is SpeechRecognitionEventKind.CANCELLED:
                    terminal = (SpeechRecognitionEventKind.CANCELLED, None, "cancelled")
                    break
                if requested is SpeechRecognitionEventKind.FINAL:
                    terminal = self._map_final(self._recognizer.finalize())
                    break
                if result.kind is PcmReadKind.DATA:
                    last_data = self._clock()
                    accepted = self._recognizer.accept_pcm(result.data)
                    if accepted and accepted.kind is RecognitionUpdateKind.PARTIAL:
                        self._publish_partial(operation_id, accepted)
                    elif accepted and accepted.kind is RecognitionUpdateKind.FAILURE:
                        if self._claim_cause(
                            operation_id, SpeechRecognitionEventKind.FAILED
                        ):
                            terminal = self._map_final(accepted)
                elif result.kind is PcmReadKind.TIMEOUT:
                    if self._clock() - last_data >= self._inactivity:
                        if self._claim_cause(
                            operation_id, SpeechRecognitionEventKind.TIMEOUT
                        ):
                            terminal = (
                                SpeechRecognitionEventKind.TIMEOUT,
                                None,
                                "inactivity_timeout",
                            )
                elif result.kind is PcmReadKind.CANCELLED:
                    if self._claim_cause(
                        operation_id, SpeechRecognitionEventKind.CANCELLED
                    ):
                        terminal = (
                            SpeechRecognitionEventKind.CANCELLED,
                            None,
                            "cancelled",
                        )
                elif result.kind is PcmReadKind.EOF:
                    if self._claim_cause(
                        operation_id, SpeechRecognitionEventKind.FAILED
                    ):
                        terminal = (
                            SpeechRecognitionEventKind.FAILED,
                            None,
                            "capture_eof_unexpected",
                        )
                else:
                    if self._claim_cause(
                        operation_id, SpeechRecognitionEventKind.FAILED
                    ):
                        terminal = (
                            SpeechRecognitionEventKind.FAILED,
                            None,
                            result.safe_reason or "capture_failed",
                        )
        except Exception:
            requested = self._requested_cause(operation_id)
            if requested is SpeechRecognitionEventKind.CANCELLED:
                terminal = (SpeechRecognitionEventKind.CANCELLED, None, "cancelled")
            elif self._claim_cause(
                operation_id, SpeechRecognitionEventKind.FAILED
            ):
                terminal = (
                    SpeechRecognitionEventKind.FAILED,
                    None,
                    "speech_input_failed",
                )
        finally:
            try:
                self._capture.stop()
            except Exception:
                pass
            if terminal is None:
                cause = self._requested_cause(operation_id)
                if cause is SpeechRecognitionEventKind.CANCELLED:
                    terminal = (cause, None, "cancelled")
                elif cause is SpeechRecognitionEventKind.FINAL:
                    try:
                        terminal = self._map_final(self._recognizer.finalize())
                    except Exception:
                        terminal = (
                            SpeechRecognitionEventKind.FAILED,
                            None,
                            "speech_input_failed",
                        )
                else:
                    self._claim_cause(
                        operation_id, SpeechRecognitionEventKind.FAILED
                    )
                    terminal = (
                        SpeechRecognitionEventKind.FAILED,
                        None,
                        "speech_input_failed",
                    )
            self._commit_terminal(operation_id, *terminal)

    def _requested_cause(
        self, operation_id: str
    ) -> SpeechRecognitionEventKind | None:
        with self._lock:
            operation = self._operation
            if operation is None or operation.operation_id != operation_id:
                return None
            return operation.cause

    def _claim_cause(
        self, operation_id: str, cause: SpeechRecognitionEventKind
    ) -> bool:
        with self._lock:
            operation = self._operation
            if (
                operation is None
                or operation.operation_id != operation_id
                or operation.terminal
            ):
                return False
            if operation.cause is None:
                operation.cause = cause
            return operation.cause is cause

    @staticmethod
    def _map_final(
        update: RecognitionUpdate,
    ) -> tuple[SpeechRecognitionEventKind, str | None, str | None]:
        mapping = {
            RecognitionUpdateKind.FINAL: SpeechRecognitionEventKind.FINAL,
            RecognitionUpdateKind.NO_SPEECH: SpeechRecognitionEventKind.NO_SPEECH,
            RecognitionUpdateKind.FAILURE: SpeechRecognitionEventKind.FAILED,
        }
        return (
            mapping.get(update.kind, SpeechRecognitionEventKind.FAILED),
            update.text,
            update.safe_reason,
        )

    def _publish_partial(self, operation_id: str, update: RecognitionUpdate) -> None:
        text = (update.text or "")[: self._max_partial]
        with self._lock:
            operation = self._operation
            if operation and operation.operation_id == operation_id and not operation.terminal:
                self._partial = SpeechRecognitionEvent(
                    operation_id, SpeechRecognitionEventKind.PARTIAL, text
                )

    def _commit_terminal(
        self,
        operation_id: str,
        kind: SpeechRecognitionEventKind,
        text: str | None,
        safe_reason: str | None,
    ) -> bool:
        lease: AudioTurnLease | None = None
        with self._lock:
            operation = self._operation
            if (
                operation is None
                or operation.operation_id != operation_id
                or operation.terminal
            ):
                return False
            operation.terminal = True
            lease = operation.lease
            self._terminal = SpeechRecognitionEvent(
                operation_id, kind, text=text, safe_reason=safe_reason
            )
            self._partial = None
            if self._state is not SpeechInputState.CLOSED:
                self._state = SpeechInputState.IDLE
        self._turns.release(lease)
        return True
