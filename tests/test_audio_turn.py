from __future__ import annotations

import threading

import pytest

from sirah.audio_turn import (
    AudioTurnCoordinator,
    AudioTurnDirection,
    AudioTurnLease,
    AudioTurnState,
)
from sirah.errors import AudioTurnBusyError
from sirah.errors import SpeechStartError
from sirah.guarded_speech import GuardedSpeechOutput
from sirah.speech_fakes import FakePcmCapture, FakeSpeechRecognizer
from sirah.speech_input import (
    RecognitionUpdate,
    RecognitionUpdateKind,
    SpeechInputRuntime,
)
from sirah.simulation import FakeSpeechOutput
from sirah.speech import SpeechCompletion, SpeechOutcome, SpeechState


def test_lease_from_old_generation_cannot_release_new_turn() -> None:
    turns = AudioTurnCoordinator()
    first = turns.reserve_input()
    assert turns.release(first)
    second = turns.reserve_output()
    assert not turns.release(first)
    assert turns.snapshot().lease == second
    wrong = AudioTurnLease(second.token, AudioTurnDirection.INPUT, second.generation)
    assert not turns.release(wrong)
    assert turns.release(second)
    assert turns.snapshot().state is AudioTurnState.IDLE


def test_reservation_is_atomic_under_barrier() -> None:
    turns = AudioTurnCoordinator()
    barrier = threading.Barrier(3)
    winners: list[str] = []

    def reserve(name: str) -> None:
        barrier.wait()
        try:
            lease = (
                turns.reserve_input() if name == "input" else turns.reserve_output()
            )
            winners.append(lease.direction.value)
        except AudioTurnBusyError:
            pass

    threads = [threading.Thread(target=reserve, args=(name,)) for name in ("input", "output")]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)
    assert len(winners) == 1


class ImmediateDriver:
    available = True
    active = False
    state = SpeechState.IDLE

    def __init__(self, concurrent: bool = False) -> None:
        self.accepted = lambda _id: None
        self.terminal = lambda _id: None
        self.completion: SpeechCompletion | None = None
        self.concurrent = concurrent

    def set_lifecycle_hooks(self, accepted, terminal) -> None:
        self.accepted, self.terminal = accepted, terminal

    def start(self, text: str) -> str:
        operation_id = "immediate-output"
        self.completion = SpeechCompletion(
            operation_id, SpeechOutcome.COMPLETED, "prepared_terminal", None
        )
        self.accepted(operation_id)
        if self.concurrent:
            done = threading.Event()
            def finish() -> None:
                self.terminal(operation_id)
                done.set()

            thread = threading.Thread(target=finish)
            thread.start()
            assert done.wait(1)
            thread.join(1)
        else:
            self.terminal(operation_id)
        return operation_id

    def stop(self, expected_operation_id=None) -> bool:
        return False

    def poll(self):
        result, self.completion = self.completion, None
        return result

    def close(self) -> None:
        pass


class CountingTurns(AudioTurnCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.releases = 0

    def release(self, lease):
        released = super().release(lease)
        self.releases += int(released)
        return released


def test_guarded_output_handles_terminal_before_start_returns() -> None:
    turns = CountingTurns()
    driver = ImmediateDriver(concurrent=False)
    guard = GuardedSpeechOutput(driver, turns)
    assert guard.start("private") == "immediate-output"
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 1
    completion = guard.poll()
    assert completion and completion.safe_reason == "prepared_terminal"
    assert guard.poll() is None
    assert guard._pending_start is None
    assert guard._leases == {}
    guard._on_terminal("immediate-output")
    assert turns.releases == 1


def test_guarded_output_handles_concurrent_terminal_before_start_returns() -> None:
    turns = CountingTurns()
    driver = ImmediateDriver(concurrent=True)
    guard = GuardedSpeechOutput(driver, turns)
    assert guard.start("private") == "immediate-output"
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 1
    assert guard.poll() is not None
    assert guard.poll() is None
    assert guard._pending_start is None and guard._leases == {}
    guard._on_terminal("immediate-output")
    assert turns.releases == 1


class MismatchedDriver(ImmediateDriver):
    def __init__(self, *, cancel_succeeds: bool) -> None:
        super().__init__()
        self.cancel_succeeds = cancel_succeeds
        self.stops: list[str | None] = []
        self.closed = False

    def start(self, text: str) -> str:
        self.accepted("accepted-A")
        return "returned-B"

    def stop(self, expected_operation_id=None) -> bool:
        self.stops.append(expected_operation_id)
        return self.cancel_succeeds

    def close(self) -> None:
        self.closed = True


def test_mismatched_handshake_keeps_a_lease_until_physical_terminal() -> None:
    turns = CountingTurns()
    driver = MismatchedDriver(cancel_succeeds=True)
    guard = GuardedSpeechOutput(driver, turns)
    with pytest.raises(SpeechStartError):
        guard.start("private")
    assert driver.stops == ["accepted-A"]
    assert turns.snapshot().state is AudioTurnState.OUTPUT
    assert "returned-B" not in guard._leases
    driver.terminal("accepted-A")
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 1
    driver.terminal("accepted-A")
    assert turns.releases == 1


def test_mismatched_handshake_closes_driver_when_cancel_fails() -> None:
    turns = CountingTurns()
    driver = MismatchedDriver(cancel_succeeds=False)
    guard = GuardedSpeechOutput(driver, turns)
    with pytest.raises(SpeechStartError):
        guard.start("private")
    assert driver.stops == ["accepted-A"]
    assert driver.closed
    assert turns.snapshot().state is AudioTurnState.OUTPUT
    driver.terminal("accepted-A")
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 1


def test_late_terminal_callback_a_cannot_release_operation_b() -> None:
    turns = CountingTurns()
    driver = ImmediateDriver()
    guard = GuardedSpeechOutput(driver, turns)
    assert guard.start("A") == "immediate-output"
    assert guard.poll() is not None
    lease_b = turns.reserve_output()
    driver.terminal("immediate-output")
    assert turns.snapshot().lease == lease_b
    assert turns.release(lease_b)
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 2


class CountingCapture(FakePcmCapture):
    def __init__(self, *, fail_stop: bool = False) -> None:
        super().__init__()
        self.starts = 0
        self.stops = 0
        self.fail_stop = fail_stop

    def start(self) -> None:
        self.starts += 1
        super().start()

    def stop(self) -> None:
        self.stops += 1
        super().stop()
        if self.fail_stop:
            raise RuntimeError("private")


class CountingRecognizer(FakeSpeechRecognizer):
    def __init__(self) -> None:
        super().__init__(
            final=RecognitionUpdate(RecognitionUpdateKind.FINAL, text="ordinary")
        )
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1
        super().reset()


def join_input(runtime: SpeechInputRuntime) -> None:
    worker = runtime._worker
    assert worker is not None
    worker.join(1)
    assert not worker.is_alive()


def test_input_lease_rejects_output_without_starting_driver() -> None:
    turns = CountingTurns()
    lease = turns.reserve_input()
    driver = FakeSpeechOutput()
    output = GuardedSpeechOutput(driver, turns)
    with pytest.raises(AudioTurnBusyError):
        output.start("private")
    assert driver.spoken_texts == []
    assert not driver.active
    assert turns.snapshot().lease == lease
    assert turns.release(lease)
    assert turns.releases == 1


def test_output_lease_rejects_stt_before_capture_worker_or_reset() -> None:
    turns = CountingTurns()
    driver = FakeSpeechOutput()
    output = GuardedSpeechOutput(driver, turns)
    operation = output.start("private")
    capture, recognizer = CountingCapture(), CountingRecognizer()
    runtime = SpeechInputRuntime(capture, recognizer, turns)
    with pytest.raises(AudioTurnBusyError):
        runtime.start()
    assert capture.starts == 0
    assert recognizer.resets == 0
    assert runtime._worker is None
    assert turns.snapshot().state is AudioTurnState.OUTPUT
    assert output.stop(operation)
    assert output.poll() is not None
    assert turns.releases == 1


def test_input_output_start_race_has_one_physical_winner_and_no_deadlock() -> None:
    turns = CountingTurns()
    capture, recognizer = CountingCapture(), CountingRecognizer()
    runtime = SpeechInputRuntime(capture, recognizer, turns)
    driver = FakeSpeechOutput()
    output = GuardedSpeechOutput(driver, turns)
    barrier = threading.Barrier(3)
    winners: list[tuple[str, str]] = []
    losers: list[type[Exception]] = []

    def start_input() -> None:
        barrier.wait()
        try:
            winners.append(("input", runtime.start()))
        except Exception as error:
            losers.append(type(error))

    def start_output() -> None:
        barrier.wait()
        try:
            winners.append(("output", output.start("private")))
        except Exception as error:
            losers.append(type(error))

    threads = [threading.Thread(target=start_input), threading.Thread(target=start_output)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)
        assert not thread.is_alive()
    assert len(winners) == len(losers) == 1
    assert losers == [AudioTurnBusyError]
    direction, operation = winners[0]
    if direction == "input":
        assert capture.starts == 1 and recognizer.resets == 1
        assert not driver.active and driver.spoken_texts == []
        assert runtime.cancel(operation)
        join_input(runtime)
        assert runtime.poll() is not None and runtime.poll() is None
    else:
        assert capture.starts == 0 and recognizer.resets == 0
        assert runtime._worker is None
        assert output.stop(operation)
        assert output.poll() is not None and output.poll() is None
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 1


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_final_input_releases_before_following_output_even_if_cleanup_fails(
    cleanup_fails: bool,
) -> None:
    turns = CountingTurns()
    capture = CountingCapture(fail_stop=cleanup_fails)
    recognizer = CountingRecognizer()
    runtime = SpeechInputRuntime(capture, recognizer, turns)
    operation = runtime.start()
    assert runtime.finalize(operation)
    join_input(runtime)
    terminal = runtime.poll()
    assert terminal and terminal.text == "ordinary"
    assert runtime.poll() is None
    assert turns.snapshot().state is AudioTurnState.IDLE
    driver = FakeSpeechOutput()
    output = GuardedSpeechOutput(driver, turns)
    output_id = output.start("after final")
    assert turns.snapshot().state is AudioTurnState.OUTPUT
    assert output.stop(output_id)
    assert output.poll() is not None
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.releases == 2
