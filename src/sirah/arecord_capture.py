"""Captura POSIX PCM S16_LE mediante un subprocess arecord administrado."""

from __future__ import annotations

import math
import os
import selectors
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Protocol

from .errors import SpeechBusyError, SpeechUnavailableError
from .speech_input import PcmReadKind, PcmReadResult

_FORBIDDEN = frozenset("\x00\n\r;&|`$><")


class CaptureProcess(Protocol):
    stdout: IO[bytes] | None
    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ArecordPcmConfig:
    executable: str = "arecord"
    device: str | None = None
    sample_rate: int = 16000
    channels: int = 1
    sample_format: str = "S16_LE"
    chunk_bytes: int = 4096
    startup_probe_seconds: float = 0.05
    read_timeout_seconds: float = 0.25
    read_poll_interval_seconds: float = 0.05
    termination_grace_seconds: float = 1.0

    def __post_init__(self) -> None:
        if (
            type(self.sample_rate) is not int
            or self.sample_rate <= 0
            or type(self.channels) is not int
            or self.channels <= 0
            or type(self.chunk_bytes) is not int
            or self.chunk_bytes < 2
            or self.chunk_bytes % 2
        ):
            raise ValueError("Configuración PCM inválida.")
        if self.sample_format != "S16_LE":
            raise ValueError("Solo se admite S16_LE.")
        for name in (
            "startup_probe_seconds",
            "read_timeout_seconds",
            "read_poll_interval_seconds",
            "termination_grace_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} debe ser finito y positivo.")
        if self.read_poll_interval_seconds > min(self.read_timeout_seconds, 0.1):
            raise ValueError("El intervalo de polling debe ser acotado.")
        for token in (self.executable, self.device):
            if token is not None and (
                not token or any(character in token for character in _FORBIDDEN)
            ):
                raise ValueError("Token de captura inválido.")


class ArecordPcmCapture:
    def __init__(
        self,
        config: ArecordPcmConfig,
        *,
        process_factory: Callable[..., CaptureProcess] = subprocess.Popen,
        selector_factory: Callable[[], selectors.BaseSelector] = selectors.DefaultSelector,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._factory = process_factory
        self._selector_factory = selector_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._process: CaptureProcess | None = None
        self._selector: selectors.BaseSelector | None = None
        self._stdout: IO[bytes] | None = None
        self._odd = b""
        self._generation = 0
        self._closed = False
        self._available = self._resolve(config.executable) is not None
        self._safe_reason = None if self._available else "arecord_unavailable"

    @staticmethod
    def _resolve(value: str) -> str | None:
        if os.sep in value:
            return value if os.path.isfile(value) and os.access(value, os.X_OK) else None
        return shutil.which(value)

    @property
    def available(self) -> bool:
        with self._lock:
            return self._available and not self._closed

    @property
    def active(self) -> bool:
        with self._lock:
            return self._process is not None

    @property
    def safe_reason(self) -> str | None:
        return self._safe_reason

    def start(self) -> None:
        with self._lock:
            if self._closed or not self._available:
                raise SpeechUnavailableError(self._safe_reason or "capture_closed")
            if self._process is not None:
                raise SpeechBusyError("La captura PCM ya está activa.")
            self._cancel.clear()
            self._odd = b""
            self._generation += 1
        argv = [
            self._config.executable, "-q", "-t", "raw", "-f",
            self._config.sample_format, "-c", str(self._config.channels),
            "-r", str(self._config.sample_rate),
        ]
        if self._config.device is not None:
            argv.extend(("-D", self._config.device))
        process: CaptureProcess | None = None
        selector: selectors.BaseSelector | None = None
        stdout: IO[bytes] | None = None
        try:
            process = self._factory(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            stdout = process.stdout
            if stdout is None:
                raise OSError
            try:
                code = process.wait(timeout=self._config.startup_probe_seconds)
            except subprocess.TimeoutExpired:
                code = None
            if code is not None:
                raise OSError
            os.set_blocking(stdout.fileno(), False)
            selector = self._selector_factory()
            selector.register(stdout, selectors.EVENT_READ)
            with self._lock:
                if self._closed or self._cancel.is_set():
                    raise OSError
                self._process, self._stdout, self._selector = process, stdout, selector
        except Exception:
            if selector is not None:
                try:
                    selector.close()
                except Exception:
                    pass
            if process is not None:
                self._reap(process)
            if stdout is not None:
                try:
                    stdout.close()
                except Exception:
                    pass
            raise SpeechUnavailableError("arecord_start_failed")

    def read_chunk(self) -> PcmReadResult:
        with self._lock:
            process, selector = self._process, self._selector
            generation = self._generation
            odd = self._odd
            self._odd = b""
        if process is None or selector is None:
            return PcmReadResult(PcmReadKind.FAILED, safe_reason="capture_not_active")
        deadline = self._clock() + self._config.read_timeout_seconds
        buffer = bytearray(odd)
        while len(buffer) < self._config.chunk_bytes:
            if self._cancel.is_set():
                return PcmReadResult(PcmReadKind.CANCELLED)
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            try:
                events = selector.select(
                    min(remaining, self._config.read_poll_interval_seconds)
                )
            except (OSError, ValueError):
                if self._cancel.is_set():
                    return PcmReadResult(PcmReadKind.CANCELLED)
                return PcmReadResult(PcmReadKind.FAILED, safe_reason="capture_selector_failed")
            if not events:
                continue
            try:
                piece = os.read(
                    process.stdout.fileno(),  # type: ignore[union-attr]
                    self._config.chunk_bytes + 1 - len(buffer),
                )
            except (BlockingIOError, InterruptedError):
                continue
            except (OSError, ValueError):
                if self._cancel.is_set():
                    return PcmReadResult(PcmReadKind.CANCELLED)
                return PcmReadResult(PcmReadKind.FAILED, safe_reason="capture_read_failed")
            if not piece:
                if len(buffer) % 2:
                    return PcmReadResult(PcmReadKind.FAILED, safe_reason="pcm_odd_byte_eof")
                if buffer:
                    break
                try:
                    code = process.poll()
                except Exception:
                    return PcmReadResult(
                        PcmReadKind.FAILED, safe_reason="arecord_poll_failed"
                    )
                return PcmReadResult(
                    PcmReadKind.EOF if code in (None, 0) else PcmReadKind.FAILED,
                    safe_reason=None if code in (None, 0) else "arecord_failed",
                )
            buffer.extend(piece)
        if len(buffer) % 2:
            with self._lock:
                if (
                    self._generation == generation
                    and self._process is process
                    and not self._cancel.is_set()
                ):
                    self._odd = bytes(buffer[-1:])
            del buffer[-1:]
        if buffer:
            return PcmReadResult(PcmReadKind.DATA, bytes(buffer))
        return PcmReadResult(PcmReadKind.TIMEOUT)

    def stop(self) -> None:
        self._cancel.set()
        with self._lock:
            process, selector, stdout = self._process, self._selector, self._stdout
            self._process = self._selector = self._stdout = None
            self._odd = b""
        if selector is not None:
            try:
                selector.close()
            except Exception:
                pass
        if process is not None:
            self._reap(process)
        if stdout is not None:
            try:
                stdout.close()
            except Exception:
                pass

    def _reap(self, process: CaptureProcess) -> None:
        try:
            running = process.poll() is None
        except Exception:
            running = True
        if running:
            try:
                process.terminate()
            except Exception:
                pass
            try:
                process.wait(timeout=self._config.termination_grace_seconds)
                return
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
            # Un wait genérico no demuestra que el proceso terminara. Tras
            # terminate, kill es el único siguiente paso acotado y seguro.
            try:
                process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=self._config.termination_grace_seconds)
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.stop()
