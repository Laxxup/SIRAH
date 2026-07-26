"""Pruebas deterministas del adaptador Piper; nunca ejecutan audio real."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from sirah.errors import SpeechBusyError, SpeechUnavailableError
from sirah.piper_speech import PiperSpeechConfig, PiperSpeechOutput
from sirah.speech import SpeechOutcome, SpeechState


class TextSink:
    def __init__(self) -> None:
        self.value = ""
        self.closed = False

    def write(self, value: str) -> int:
        self.value += value
        return len(value)

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(
        self,
        returncode: int | None = 0,
        *,
        ignore_terminate: bool = False,
    ) -> None:
        self.returncode = returncode
        self.stdin = TextSink()
        self.ignore_terminate = ignore_terminate
        self.done = threading.Event()
        if returncode is not None:
            self.done.set()
        self.calls: list[str] = []

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if not self.done.wait(timeout):
            raise subprocess.TimeoutExpired("fake", timeout or 0.0)
        assert self.returncode is not None
        return self.returncode

    def terminate(self) -> None:
        self.calls.append("terminate")
        if not self.ignore_terminate:
            self.returncode = -15
            self.done.set()

    def kill(self) -> None:
        self.calls.append("kill")
        self.returncode = -9
        self.done.set()


class Factory:
    def __init__(
        self,
        *processes: FakeProcess,
        fail_at: int | None = None,
        wav_result: bytes | None = b"wav",
    ) -> None:
        self.processes = list(processes)
        self.fail_at = fail_at
        self.wav_result = wav_result
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.spawned = threading.Event()

    def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((argv, kwargs))
        self.spawned.set()
        if self.fail_at == len(self.calls):
            raise OSError("private path must not escape")
        process = self.processes.pop(0)
        if (
            len(self.calls) == 1
            and process.returncode == 0
            and "--output_file" in argv
        ):
            wav_path = Path(argv[argv.index("--output_file") + 1])
            if self.wav_result is None:
                wav_path.unlink()
            else:
                wav_path.write_bytes(self.wav_result)
        return process


@pytest.fixture
def configured(tmp_path: Path) -> PiperSpeechConfig:
    piper = tmp_path / "piper"
    player = tmp_path / "pw-play"
    for executable in (piper, player):
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o700)
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    return PiperSpeechConfig(
        str(piper),
        model,
        player_argv=(str(player), "--fixed"),
        temporary_directory=private,
        synthesis_timeout_seconds=1,
        playback_timeout_seconds=1,
        termination_grace_seconds=0.01,
    )


def join(adapter: PiperSpeechOutput) -> None:
    worker = adapter._worker
    assert worker is not None
    worker.join(1)
    assert not worker.is_alive()


def test_valid_configuration_and_success_are_correlated(
    configured: PiperSpeechConfig,
) -> None:
    factory = Factory(FakeProcess(0), FakeProcess(0))
    adapter = PiperSpeechOutput(configured, process_factory=factory)
    operation_id = adapter.start("texto privado")
    assert type(operation_id) is str
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.operation_id == operation_id
    assert completion.outcome is SpeechOutcome.COMPLETED
    assert adapter.poll() is None
    assert adapter.state is SpeechState.IDLE
    assert len(factory.calls) == 2
    assert all("texto privado" not in token for call in factory.calls for token in call[0])
    assert factory.processes == []
    assert all(call[1]["shell"] is False for call in factory.calls)
    assert all(call[1]["stderr"] is subprocess.DEVNULL for call in factory.calls)
    assert not tuple(configured.temporary_directory.glob("*.wav"))


def test_pending_completion_must_be_polled_before_reuse(
    configured: PiperSpeechConfig,
) -> None:
    adapter = PiperSpeechOutput(
        configured,
        process_factory=Factory(FakeProcess(0), FakeProcess(0)),
    )
    adapter.start("first")
    join(adapter)
    with pytest.raises(SpeechBusyError):
        adapter.start("second")
    assert adapter.poll() is not None


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"piper_executable": "definitely-missing-piper"}, "piper_executable"),
        ({"model_path": Path("missing-model")}, "piper_model"),
        ({"config_path": Path("missing-config")}, "piper_config"),
        ({"player_argv": ("definitely-missing-player",)}, "audio_player"),
    ],
)
def test_unavailable_inputs_degrade_safely(
    configured: PiperSpeechConfig,
    change: dict[str, object],
    reason: str,
) -> None:
    values = {
        name: getattr(configured, name)
        for name in configured.__dataclass_fields__
    }
    values.update(change)
    adapter = PiperSpeechOutput(PiperSpeechConfig(**values))
    assert not adapter.available
    assert adapter.unavailable_reason and reason in adapter.unavailable_reason
    with pytest.raises(SpeechUnavailableError):
        adapter.start("must not leak")


def test_non_regular_model_and_non_private_directory_degrade(
    configured: PiperSpeechConfig, tmp_path: Path
) -> None:
    directory_model = tmp_path / "directory-model"
    directory_model.mkdir()
    values = {
        name: getattr(configured, name)
        for name in configured.__dataclass_fields__
    }
    values["model_path"] = directory_model
    assert not PiperSpeechOutput(PiperSpeechConfig(**values)).available
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    values["model_path"] = configured.model_path
    values["temporary_directory"] = public
    adapter = PiperSpeechOutput(PiperSpeechConfig(**values))
    assert not adapter.available
    assert adapter.unavailable_reason == "temporary_directory_not_private"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"player_argv": ()},
        {"player_argv": ("pw-play;other",)},
        {"piper_executable": "piper\x00bad"},
        {"synthesis_timeout_seconds": 0},
        {"synthesis_timeout_seconds": float("nan")},
        {"playback_timeout_seconds": float("inf")},
        {"playback_timeout_seconds": -1},
        {"termination_grace_seconds": 0},
    ],
)
def test_invalid_structural_configuration_is_rejected(
    configured: PiperSpeechConfig, kwargs: dict[str, object]
) -> None:
    values = {
        name: getattr(configured, name)
        for name in configured.__dataclass_fields__
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        PiperSpeechConfig(**values)


def test_one_active_operation_and_expected_stop(
    configured: PiperSpeechConfig,
) -> None:
    process = FakeProcess(None)
    adapter = PiperSpeechOutput(configured, process_factory=Factory(process))
    operation_id = adapter.start("hello")
    assert adapter.active
    assert adapter.state is SpeechState.SYNTHESIZING
    with pytest.raises(SpeechBusyError):
        adapter.start("second")
    assert not adapter.stop("stale-operation")
    assert adapter.active
    assert adapter.stop(operation_id)
    assert adapter.stop(operation_id)
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.outcome is SpeechOutcome.CANCELLED
    assert not adapter.stop()
    assert "terminate" in process.calls
    assert "wait" in process.calls


def test_terminate_wait_kill_wait(configured: PiperSpeechConfig) -> None:
    process = FakeProcess(None, ignore_terminate=True)
    adapter = PiperSpeechOutput(configured, process_factory=Factory(process))
    adapter.start("hello")
    assert adapter.stop()
    join(adapter)
    assert process.calls[:4] == ["terminate", "wait", "kill", "wait"]


def test_synthesis_failure_does_not_play(configured: PiperSpeechConfig) -> None:
    factory = Factory(FakeProcess(2))
    adapter = PiperSpeechOutput(configured, process_factory=factory)
    adapter.start("hello")
    join(adapter)
    assert adapter.poll().outcome is SpeechOutcome.FAILED  # type: ignore[union-attr]
    assert len(factory.calls) == 1
    assert not tuple(configured.temporary_directory.glob("*.wav"))


@pytest.mark.parametrize("wav_result", [b"", None])
def test_missing_or_empty_synthesis_output_does_not_play(
    configured: PiperSpeechConfig, wav_result: bytes | None
) -> None:
    factory = Factory(FakeProcess(0), wav_result=wav_result)
    adapter = PiperSpeechOutput(configured, process_factory=factory)
    adapter.start("hello")
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.outcome is SpeechOutcome.FAILED
    assert completion.safe_reason == "synthesis_output_invalid"
    assert len(factory.calls) == 1
    assert not tuple(configured.temporary_directory.glob("*.wav"))


def test_player_failure_is_terminal(configured: PiperSpeechConfig) -> None:
    adapter = PiperSpeechOutput(
        configured, process_factory=Factory(FakeProcess(0), FakeProcess(3))
    )
    adapter.start("hello")
    join(adapter)
    assert adapter.poll().safe_reason == "playback_failed"  # type: ignore[union-attr]


def test_popen_failure_removes_wav(configured: PiperSpeechConfig) -> None:
    adapter = PiperSpeechOutput(
        configured, process_factory=Factory(fail_at=1)
    )
    adapter.start("private")
    join(adapter)
    assert adapter.poll().safe_reason == "piper_start_failed"  # type: ignore[union-attr]
    assert not tuple(configured.temporary_directory.glob("*.wav"))


def test_synthesis_timeout_is_monotonic(configured: PiperSpeechConfig) -> None:
    values = iter((0.0, 2.0, 3.0))
    process = FakeProcess(None)
    adapter = PiperSpeechOutput(
        configured,
        process_factory=Factory(process),
        clock=lambda: next(values, 3.0),
    )
    adapter.start("hello")
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.outcome is SpeechOutcome.TIMEOUT
    assert completion.safe_reason == "synthesis_timeout"
    assert not tuple(configured.temporary_directory.glob("*.wav"))


def test_playback_timeout_is_separate(configured: PiperSpeechConfig) -> None:
    values = iter((0.0, 0.0, 2.0, 3.0))
    player = FakeProcess(None)
    adapter = PiperSpeechOutput(
        configured,
        process_factory=Factory(FakeProcess(0), player),
        clock=lambda: next(values, 3.0),
    )
    adapter.start("hello")
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.safe_reason == "playback_timeout"


def test_cancel_during_playback_and_close_are_bounded(
    configured: PiperSpeechConfig,
) -> None:
    player = FakeProcess(None)
    second_spawn = threading.Event()

    class PlaybackFactory(Factory):
        def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
            result = super().__call__(argv, **kwargs)
            if len(self.calls) == 2:
                second_spawn.set()
            return result

    adapter = PiperSpeechOutput(
        configured,
        process_factory=PlaybackFactory(FakeProcess(0), player),
    )
    operation_id = adapter.start("hello")
    assert second_spawn.wait(1)
    assert adapter.state is SpeechState.PLAYING
    adapter.close()
    assert adapter.state is SpeechState.CLOSED
    assert not adapter.available
    completion = adapter.poll()
    assert completion and completion.operation_id == operation_id
    assert completion.outcome is SpeechOutcome.CANCELLED
    adapter.close()
    with pytest.raises(SpeechUnavailableError):
        adapter.start("after close")
    assert not tuple(configured.temporary_directory.glob("*.wav"))


def test_close_idle_is_idempotent(configured: PiperSpeechConfig) -> None:
    adapter = PiperSpeechOutput(configured)
    adapter.close()
    adapter.close()
    assert adapter.state is SpeechState.CLOSED


def test_cancel_wins_when_timeout_becomes_due(
    configured: PiperSpeechConfig,
) -> None:
    checking_deadline = threading.Event()
    release_clock = threading.Event()
    clock_calls = 0

    def racing_clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 1:
            return 0.0
        checking_deadline.set()
        assert release_clock.wait(1)
        return 2.0

    adapter = PiperSpeechOutput(
        configured,
        process_factory=Factory(FakeProcess(None)),
        clock=racing_clock,
    )
    operation_id = adapter.start("hello")
    assert checking_deadline.wait(1)
    assert adapter.stop(operation_id)
    release_clock.set()
    join(adapter)
    completion = adapter.poll()
    assert completion and completion.outcome is SpeechOutcome.CANCELLED


def test_close_preserves_terminal_already_produced(
    configured: PiperSpeechConfig,
) -> None:
    adapter = PiperSpeechOutput(
        configured,
        process_factory=Factory(FakeProcess(0), FakeProcess(0)),
    )
    operation_id = adapter.start("hello")
    join(adapter)
    adapter.close()
    completion = adapter.poll()
    assert completion and completion.operation_id == operation_id
    assert completion.outcome is SpeechOutcome.COMPLETED
    assert adapter.poll() is None


def test_close_waits_until_worker_has_finished(
    configured: PiperSpeechConfig,
) -> None:
    spawn_entered = threading.Event()
    release_spawn = threading.Event()

    class BlockingFactory(Factory):
        def __call__(self, argv: list[str], **kwargs: Any) -> FakeProcess:
            spawn_entered.set()
            assert release_spawn.wait(1)
            return super().__call__(argv, **kwargs)

    adapter = PiperSpeechOutput(
        configured,
        process_factory=BlockingFactory(FakeProcess(0)),
    )
    adapter.start("hello")
    assert spawn_entered.wait(1)
    closer = threading.Thread(target=adapter.close)
    closer.start()
    assert adapter._cancel.wait(1)
    assert closer.is_alive()
    release_spawn.set()
    closer.join(1)
    assert not closer.is_alive()
    worker = adapter._worker
    assert worker is not None and not worker.is_alive()
    assert adapter.state is SpeechState.CLOSED
