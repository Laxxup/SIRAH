"""Adaptador experimental Piper CLI con reproducción local administrada."""

from __future__ import annotations

import math
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from .errors import SpeechBusyError, SpeechUnavailableError
from .speech import SpeechCompletion, SpeechOutcome, SpeechState

_FORBIDDEN_TOKEN_CHARACTERS = frozenset("\x00\n\r;&|`$><")


class ManagedProcess(Protocol):
    stdin: IO[str] | None

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[..., ManagedProcess]


@dataclass(frozen=True, slots=True)
class PiperSpeechConfig:
    piper_executable: str
    model_path: Path
    config_path: Path | None = None
    player_argv: tuple[str, ...] = ("pw-play",)
    synthesis_timeout_seconds: float = 30.0
    playback_timeout_seconds: float = 30.0
    termination_grace_seconds: float = 1.0
    temporary_directory: Path | None = None

    def __post_init__(self) -> None:
        for name in (
            "synthesis_timeout_seconds",
            "playback_timeout_seconds",
            "termination_grace_seconds",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} debe ser positivo.")
        if not self.player_argv:
            raise ValueError("player_argv no puede estar vacío.")
        for token in (self.piper_executable, *self.player_argv):
            if not token or any(character in token for character in _FORBIDDEN_TOKEN_CHARACTERS):
                raise ValueError("Los argumentos de proceso contienen sintaxis no permitida.")

    @classmethod
    def from_environment(
        cls,
        *,
        piper_executable: str | None = None,
        model_path: Path | None = None,
        config_path: Path | None = None,
        player_argv: tuple[str, ...] | None = None,
        temporary_directory: Path | None = None,
    ) -> "PiperSpeechConfig":
        configured_model = model_path or Path(
            os.environ.get(
                "SIRAH_PIPER_MODEL", "__sirah_piper_model_not_configured__"
            )
        )
        configured_config = config_path
        if configured_config is None and os.environ.get("SIRAH_PIPER_CONFIG"):
            configured_config = Path(os.environ["SIRAH_PIPER_CONFIG"])
        configured_player = player_argv
        if configured_player is None:
            configured_player = (
                os.environ.get("SIRAH_AUDIO_PLAYER", "pw-play"),
            )
        return cls(
            piper_executable=piper_executable
            or os.environ.get("SIRAH_PIPER_BIN", "piper"),
            model_path=configured_model,
            config_path=configured_config,
            player_argv=configured_player,
            temporary_directory=temporary_directory,
        )


class PiperSpeechOutput:
    """Una operación, un worker y una completion pendiente como máximo."""

    def __init__(
        self,
        config: PiperSpeechConfig,
        *,
        process_factory: ProcessFactory = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._process_factory = process_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = SpeechState.IDLE
        self._operation_id: str | None = None
        self._completion: SpeechCompletion | None = None
        self._worker: threading.Thread | None = None
        self._process: ManagedProcess | None = None
        self._available, self._unavailable_reason = self._check_availability()

    @property
    def available(self) -> bool:
        with self._lock:
            return self._available and self._state is not SpeechState.CLOSED

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    @property
    def active(self) -> bool:
        with self._lock:
            return self._operation_id is not None

    @property
    def state(self) -> SpeechState:
        with self._lock:
            return self._state

    def start(self, text: str) -> str:
        with self._lock:
            if self._state is SpeechState.CLOSED or not self._available:
                raise SpeechUnavailableError(
                    self._unavailable_reason or "TTS no disponible."
                )
            if (
                self._state is not SpeechState.IDLE
                or self._operation_id is not None
                or self._completion is not None
            ):
                raise SpeechBusyError("TTS ya tiene una operación activa.")
            operation_id = uuid.uuid4().hex
            self._operation_id = operation_id
            self._state = SpeechState.SYNTHESIZING
            self._cancel.clear()
            worker = threading.Thread(
                target=self._run,
                args=(operation_id, text),
                name="sirah-piper-speech",
                daemon=False,
            )
            self._worker = worker
            worker.start()
            return operation_id

    def stop(self, expected_operation_id: str | None = None) -> bool:
        with self._lock:
            operation_id = self._operation_id
            if operation_id is None:
                return False
            if expected_operation_id is not None and expected_operation_id != operation_id:
                return False
            self._state = SpeechState.CANCELLING
            self._cancel.set()
            process = self._process
        if process is not None:
            self._terminate_process(process)
        return True

    def poll(self) -> SpeechCompletion | None:
        with self._lock:
            completion = self._completion
            self._completion = None
            return completion

    def close(self) -> None:
        with self._lock:
            if self._state is SpeechState.CLOSED:
                return
            operation_id = self._operation_id
        if operation_id is not None:
            self.stop(operation_id)
        with self._lock:
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()
        with self._lock:
            self._state = SpeechState.CLOSED
            self._available = False
            self._operation_id = None
            self._process = None

    def _check_availability(self) -> tuple[bool, str | None]:
        if self._resolve_executable(self._config.piper_executable) is None:
            return False, "piper_executable_unavailable"
        if not self._regular_readable(self._config.model_path):
            return False, "piper_model_unavailable"
        if self._config.config_path is not None and not self._regular_readable(
            self._config.config_path
        ):
            return False, "piper_config_unavailable"
        if self._resolve_executable(self._config.player_argv[0]) is None:
            return False, "audio_player_unavailable"
        directory = self._config.temporary_directory
        if directory is not None:
            try:
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            except OSError:
                return False, "temporary_directory_unavailable"
            try:
                mode = stat.S_IMODE(directory.stat().st_mode)
            except OSError:
                return False, "temporary_directory_unavailable"
            if not directory.is_dir() or mode & 0o077 or not os.access(
                directory, os.W_OK | os.X_OK
            ):
                return False, "temporary_directory_not_private"
        return True, None

    @staticmethod
    def _regular_readable(path: Path) -> bool:
        try:
            return path.is_file() and os.access(path, os.R_OK)
        except OSError:
            return False

    @staticmethod
    def _resolve_executable(value: str) -> str | None:
        if os.sep in value:
            path = Path(value)
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        return shutil.which(value)

    def _run(self, operation_id: str, text: str) -> None:
        wav_path: Path | None = None
        outcome = SpeechOutcome.FAILED
        reason = "unexpected_speech_failure"
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix="sirah-speech-",
                suffix=".wav",
                dir=self._config.temporary_directory,
            )
            os.close(descriptor)
            os.chmod(raw_path, 0o600)
            wav_path = Path(raw_path)
            outcome, reason = self._synthesize(operation_id, text, wav_path)
            if outcome is SpeechOutcome.COMPLETED:
                try:
                    valid_wav = wav_path.is_file() and wav_path.stat().st_size > 0
                except OSError:
                    valid_wav = False
                if valid_wav:
                    outcome, reason = self._play(operation_id, wav_path)
                else:
                    outcome, reason = SpeechOutcome.FAILED, "synthesis_output_invalid"
        except OSError:
            outcome, reason = SpeechOutcome.FAILED, "temporary_wav_failure"
        except Exception:
            outcome, reason = SpeechOutcome.FAILED, "unexpected_speech_failure"
        finally:
            if wav_path is not None:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    outcome, reason = SpeechOutcome.FAILED, "temporary_wav_cleanup_failed"
            self._finish(operation_id, outcome, reason)

    def _synthesize(
        self, operation_id: str, text: str, wav_path: Path
    ) -> tuple[SpeechOutcome, str]:
        argv = [
            self._config.piper_executable,
            "--model",
            str(self._config.model_path),
            "--output_file",
            str(wav_path),
        ]
        if self._config.config_path is not None:
            argv.extend(("--config", str(self._config.config_path)))
        try:
            process = self._spawn(argv, stdin=subprocess.PIPE)
        except OSError:
            return SpeechOutcome.FAILED, "piper_start_failed"
        try:
            if process.stdin is None:
                return SpeechOutcome.FAILED, "piper_stdin_unavailable"
            process.stdin.write(text)
            process.stdin.close()
            return self._await_process(
                operation_id,
                process,
                self._clock() + self._config.synthesis_timeout_seconds,
                "synthesis",
            )
        finally:
            if process.poll() is None:
                self._terminate_process(process)
            else:
                process.wait()
            self._clear_process(process)

    def _play(
        self, operation_id: str, wav_path: Path
    ) -> tuple[SpeechOutcome, str]:
        if self._cancel.is_set():
            return SpeechOutcome.CANCELLED, "cancelled"
        self._set_state(operation_id, SpeechState.PLAYING)
        try:
            process = self._spawn([*self._config.player_argv, str(wav_path)])
        except OSError:
            return SpeechOutcome.FAILED, "audio_player_start_failed"
        try:
            return self._await_process(
                operation_id,
                process,
                self._clock() + self._config.playback_timeout_seconds,
                "playback",
            )
        finally:
            self._clear_process(process)

    def _spawn(self, argv: list[str], **kwargs: object) -> ManagedProcess:
        process = self._process_factory(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            shell=False,
            **kwargs,
        )
        with self._lock:
            self._process = process
        return process

    def _await_process(
        self,
        operation_id: str,
        process: ManagedProcess,
        deadline: float,
        phase: str,
    ) -> tuple[SpeechOutcome, str]:
        while True:
            return_code = process.poll()
            if return_code is not None:
                process.wait()
                if self._cancel.is_set():
                    return SpeechOutcome.CANCELLED, "cancelled"
                if return_code == 0:
                    return SpeechOutcome.COMPLETED, f"{phase}_completed"
                return SpeechOutcome.FAILED, f"{phase}_failed"
            if self._cancel.is_set():
                self._terminate_process(process)
                return SpeechOutcome.CANCELLED, "cancelled"
            remaining = deadline - self._clock()
            if remaining <= 0:
                self._terminate_process(process)
                if self._cancel.is_set():
                    return SpeechOutcome.CANCELLED, "cancelled"
                return SpeechOutcome.TIMEOUT, f"{phase}_timeout"
            self._cancel.wait(min(remaining, 0.05))
            with self._lock:
                if self._operation_id != operation_id:
                    return SpeechOutcome.CANCELLED, "cancelled"

    def _terminate_process(self, process: ManagedProcess) -> None:
        if process.poll() is not None:
            process.wait()
            return
        try:
            process.terminate()
        except OSError:
            pass
        try:
            process.wait(timeout=self._config.termination_grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except OSError:
            pass
        process.wait()

    def _clear_process(self, process: ManagedProcess) -> None:
        with self._lock:
            if self._process is process:
                self._process = None

    def _set_state(self, operation_id: str, state: SpeechState) -> None:
        with self._lock:
            if self._operation_id == operation_id and not self._cancel.is_set():
                self._state = state

    def _finish(
        self, operation_id: str, outcome: SpeechOutcome, reason: str
    ) -> None:
        completion = SpeechCompletion(
            operation_id, outcome, reason, self._clock()
        )
        with self._lock:
            if self._operation_id != operation_id:
                return
            if self._completion is None:
                self._completion = completion
            self._operation_id = None
            self._process = None
            if self._state is not SpeechState.CLOSED:
                self._state = SpeechState.IDLE
