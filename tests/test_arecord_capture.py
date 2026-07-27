from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Any

import pytest

from sirah.arecord_capture import ArecordPcmCapture, ArecordPcmConfig
from sirah.errors import SpeechUnavailableError
from sirah.speech_input import PcmReadKind


class PipeProcess:
    def __init__(self, *, startup_code: int | None = None) -> None:
        read_fd, self.write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb", buffering=0)
        self.code = startup_code
        self.calls: list[str] = []
        self._writer_open = True

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return self.code

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.code = -15
        if self._writer_open:
            os.close(self.write_fd)
            self._writer_open = False

    def kill(self) -> None:
        self.calls.append("kill")
        self.code = -9

    def write(self, data: bytes) -> None:
        os.write(self.write_fd, data)

    def eof(self) -> None:
        os.close(self.write_fd)
        self._writer_open = False


def config(**changes: Any) -> ArecordPcmConfig:
    values: dict[str, Any] = {
        "executable": sys.executable,
        "chunk_bytes": 4,
        "startup_probe_seconds": 0.01,
        "read_timeout_seconds": 0.05,
        "read_poll_interval_seconds": 0.01,
        "termination_grace_seconds": 0.01,
    }
    values.update(changes)
    return ArecordPcmConfig(**values)


def test_fragment_and_odd_byte_are_bounded_between_reads() -> None:
    process = PipeProcess()
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    process.write(b"\x01\x02\x03")
    first = capture.read_chunk()
    assert first.kind is PcmReadKind.DATA and first.data == b"\x01\x02"
    process.write(b"\x04")
    second = capture.read_chunk()
    assert second.kind is PcmReadKind.DATA and second.data == b"\x03\x04"
    capture.stop()
    assert process.stdout.closed
    assert "terminate" in process.calls and process.calls.count("wait") >= 2


def test_timeout_and_concurrent_cancel_are_distinct() -> None:
    process = PipeProcess()
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    assert capture.read_chunk().kind is PcmReadKind.TIMEOUT
    entered = threading.Event()
    result = []

    def read() -> None:
        entered.set()
        result.append(capture.read_chunk())

    thread = threading.Thread(target=read)
    thread.start()
    assert entered.wait(1)
    capture.stop()
    thread.join(1)
    assert not thread.is_alive()
    assert result[0].kind is PcmReadKind.CANCELLED


class BlockingSelector:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.released = threading.Event()
        self.close_calls = 0

    def register(self, fileobj: object, events: int) -> None:
        pass

    def select(self, timeout: float | None = None) -> list[object]:
        self.entered.set()
        assert self.released.wait(1)
        return []

    def close(self) -> None:
        self.close_calls += 1
        self.released.set()


def test_stop_while_blocked_inside_selector_is_bounded_and_cleaned_once() -> None:
    process = PipeProcess()
    selector = BlockingSelector()
    capture = ArecordPcmCapture(
        config(),
        process_factory=lambda *a, **k: process,
        selector_factory=lambda: selector,  # type: ignore[arg-type]
    )
    capture.start()
    results = []
    reader = threading.Thread(target=lambda: results.append(capture.read_chunk()))
    reader.start()
    assert selector.entered.wait(1)
    capture.stop()
    reader.join(1)
    assert not reader.is_alive()
    assert results[0].kind is PcmReadKind.CANCELLED
    assert selector.close_calls == 1
    assert process.calls.count("terminate") == 1
    capture.stop()
    assert selector.close_calls == 1


def test_eof_with_odd_byte_fails_and_restart_after_stop() -> None:
    first = PipeProcess()
    second = PipeProcess()
    processes = iter((first, second))
    capture = ArecordPcmCapture(
        config(), process_factory=lambda *a, **k: next(processes)
    )
    capture.start()
    first.write(b"\x01")
    first.eof()
    assert capture.read_chunk().safe_reason == "pcm_odd_byte_eof"
    capture.stop()
    capture.start()
    capture.stop()
    capture.close()
    with pytest.raises(SpeechUnavailableError):
        capture.start()


def test_startup_death_is_reaped() -> None:
    process = PipeProcess(startup_code=2)
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    with pytest.raises(SpeechUnavailableError):
        capture.start()
    assert process.calls.count("wait") >= 2
    assert process.stdout.closed


def test_exact_argv_and_safe_popen_configuration() -> None:
    process = PipeProcess()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def factory(argv: list[str], **kwargs: object) -> PipeProcess:
        calls.append((argv, kwargs))
        return process

    capture = ArecordPcmCapture(
        config(device="hw:1,0"), process_factory=factory
    )
    capture.start()
    assert calls == [
        (
            [
                sys.executable,
                "-q",
                "-t",
                "raw",
                "-f",
                "S16_LE",
                "-c",
                "1",
                "-r",
                "16000",
                "-D",
                "hw:1,0",
            ],
            {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.DEVNULL,
                "shell": False,
            },
        )
    ]
    assert not os.get_blocking(process.stdout.fileno())
    capture.stop()


def test_two_concurrent_stops_reap_process_once() -> None:
    process = PipeProcess()
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    barrier = threading.Barrier(3)

    def stop() -> None:
        barrier.wait()
        capture.stop()

    threads = [threading.Thread(target=stop) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)
        assert not thread.is_alive()
    assert process.calls.count("terminate") == 1
    assert capture._odd == b""
    capture.close()
    capture.close()
    assert process.calls.count("terminate") == 1


class FaultProcess(PipeProcess):
    def __init__(self, fault: str) -> None:
        super().__init__()
        self.fault = fault
        self.wait_calls = 0

    def poll(self) -> int | None:
        if self.fault == "poll":
            raise RuntimeError("private")
        return super().poll()

    def terminate(self) -> None:
        self.calls.append("terminate")
        if self.fault == "terminate":
            raise RuntimeError("private")
        if self.fault in {"wait_first", "wait_timeout", "wait_final", "kill"}:
            return
        self.code = -15

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        self.wait_calls += 1
        if self.fault == "wait_first" and self.wait_calls == 2:
            raise RuntimeError("private")
        if self.fault == "wait_timeout" and self.wait_calls == 2:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        if self.fault == "wait_final" and self.wait_calls >= 3:
            raise RuntimeError("private")
        if self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return self.code

    def kill(self) -> None:
        self.calls.append("kill")
        if self.fault == "kill":
            raise RuntimeError("private")
        self.code = -9


@pytest.mark.parametrize(
    "fault", ["terminate", "wait_first", "wait_timeout", "kill", "wait_final"]
)
def test_exceptional_reap_matrix_is_bounded_and_clears_references(fault: str) -> None:
    process = FaultProcess(fault)
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    capture.stop()
    assert capture._process is capture._selector is capture._stdout is None
    assert capture._odd == b""
    assert not capture.active
    assert process.calls.count("terminate") <= 1
    assert process.calls.count("kill") <= 1
    capture.stop()
    assert process.calls.count("terminate") <= 1


class FaultCloseSelector(BlockingSelector):
    def close(self) -> None:
        super().close()
        raise RuntimeError("private")


def test_selector_close_exception_is_contained_and_cleanup_continues() -> None:
    process = PipeProcess()
    selector = FaultCloseSelector()
    capture = ArecordPcmCapture(
        config(),
        process_factory=lambda *a, **k: process,
        selector_factory=lambda: selector,  # type: ignore[arg-type]
    )
    capture.start()
    capture.stop()
    assert selector.close_calls == 1
    assert process.calls.count("terminate") == 1
    assert process.stdout.closed
    assert capture._process is None


def test_stdout_close_exception_is_contained() -> None:
    process = PipeProcess()
    original = process.stdout

    class FaultStream:
        def fileno(self) -> int:
            return original.fileno()

        def close(self) -> None:
            original.close()
            raise RuntimeError("private")

    process.stdout = FaultStream()  # type: ignore[assignment]
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    capture.stop()
    assert original.closed
    assert capture._stdout is None


def test_poll_exception_is_translated_for_read_and_runtime_cleanup() -> None:
    process = FaultProcess("poll")
    capture = ArecordPcmCapture(config(), process_factory=lambda *a, **k: process)
    capture.start()
    process.eof()
    result = capture.read_chunk()
    assert result.kind is PcmReadKind.FAILED
    assert result.safe_reason == "arecord_poll_failed"
    capture.stop()
    assert capture._process is None


def test_stop_discards_odd_byte_and_restart_starts_clean() -> None:
    first, second = PipeProcess(), PipeProcess()
    processes = iter((first, second))
    capture = ArecordPcmCapture(
        config(), process_factory=lambda *a, **k: next(processes)
    )
    capture.start()
    first.write(b"\x01")
    assert capture.read_chunk().kind is PcmReadKind.TIMEOUT
    assert capture._odd == b"\x01"
    capture.stop()
    assert capture._odd == b""
    capture.start()
    second.write(b"\x02\x03")
    assert capture.read_chunk().data == b"\x02\x03"
    capture.stop()
