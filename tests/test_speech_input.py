from __future__ import annotations

import threading

import pytest

from sirah import CapabilityRunner, create_default_catalog
from sirah.audio_turn import AudioTurnCoordinator, AudioTurnState
from sirah.context import SessionContextStore
from sirah.conversation import ConversationOrchestrator
from sirah.errors import SpeechBusyError, SpeechUnavailableError
from sirah.guarded_speech import GuardedSpeechOutput
from sirah.intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligenceResponse,
)
from sirah.local_commands import LocalStopRouter
from sirah.simulated_robot import SimulatedRobotAdapter
from sirah.simulation import FakeSpeechOutput
from sirah.speech_fakes import FakePcmCapture, FakeSpeechRecognizer
from sirah.speech_input import (
    PcmReadKind,
    PcmReadResult,
    RecognitionUpdate,
    RecognitionUpdateKind,
    SpeechInputRuntime,
    SpeechInputState,
    SpeechRecognitionEvent,
    SpeechRecognitionEventKind,
)
from sirah.speech_input_coordinator import SpeechInputCoordinator


def join(runtime: SpeechInputRuntime) -> None:
    worker = runtime._worker
    assert worker is not None
    worker.join(1)
    assert not worker.is_alive()


def test_finalize_emits_one_terminal_and_pending_blocks_start() -> None:
    turns = AudioTurnCoordinator()
    runtime = SpeechInputRuntime(
        FakePcmCapture((PcmReadResult(PcmReadKind.TIMEOUT),)),
        FakeSpeechRecognizer(
            final=RecognitionUpdate(RecognitionUpdateKind.FINAL, text="hola")
        ),
        turns,
    )
    operation_id = runtime.start()
    assert runtime.finalize(operation_id)
    join(runtime)
    assert turns.snapshot().state is AudioTurnState.IDLE
    with pytest.raises(SpeechBusyError):
        runtime.start()
    event = runtime.poll()
    assert event and event.operation_id == operation_id
    assert event.kind is SpeechRecognitionEventKind.FINAL
    assert runtime.poll() is None


def test_unexpected_eof_is_failure_not_no_speech() -> None:
    runtime = SpeechInputRuntime(
        FakePcmCapture((PcmReadResult(PcmReadKind.EOF),)),
        FakeSpeechRecognizer(),
        AudioTurnCoordinator(),
    )
    runtime.start()
    join(runtime)
    event = runtime.poll()
    assert event and event.kind is SpeechRecognitionEventKind.FAILED
    assert event.safe_reason == "capture_eof_unexpected"


def test_cancel_is_correlated_and_close_preserves_terminal() -> None:
    runtime = SpeechInputRuntime(
        FakePcmCapture(),
        FakeSpeechRecognizer(),
        AudioTurnCoordinator(),
    )
    operation_id = runtime.start()
    assert not runtime.cancel("stale")
    assert runtime.cancel(operation_id)
    join(runtime)
    runtime.close()
    assert runtime.state is SpeechInputState.CLOSED
    event = runtime.poll()
    assert event and event.kind is SpeechRecognitionEventKind.CANCELLED
    assert runtime.poll() is None
    with pytest.raises(SpeechUnavailableError):
        runtime.start()


def test_thread_start_failure_rolls_back_without_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    turns = AudioTurnCoordinator()
    runtime = SpeechInputRuntime(
        FakePcmCapture(), FakeSpeechRecognizer(), turns
    )

    def fail_start(self: threading.Thread) -> None:
        raise RuntimeError

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    with pytest.raises(Exception):
        runtime.start()
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert not runtime.active
    assert runtime.poll() is None


class GatedCapture(FakePcmCapture):
    def __init__(self, *, cleanup_fails: bool = False) -> None:
        super().__init__()
        self.start_entered = threading.Event()
        self.allow_start = threading.Event()
        self.read_entered = threading.Event()
        self.allow_read = threading.Event()
        self.stop_calls: list[int] = []
        self.cleanup_fails = cleanup_fails

    def start(self) -> None:
        self.start_entered.set()
        assert self.allow_start.wait(1)
        super().start()

    def read_chunk(self) -> PcmReadResult:
        self.read_entered.set()
        assert self.allow_read.wait(1)
        return PcmReadResult(PcmReadKind.TIMEOUT)

    def stop(self) -> None:
        self.stop_calls.append(threading.get_ident())
        super().stop()
        if self.cleanup_fails:
            raise RuntimeError("cleanup failure")


def test_cancel_during_start_is_non_blocking_and_wins() -> None:
    capture = GatedCapture()
    turns = AudioTurnCoordinator()
    runtime = SpeechInputRuntime(capture, FakeSpeechRecognizer(), turns)
    operation_id = runtime.start()
    assert capture.start_entered.wait(1)
    caller = threading.get_ident()
    assert runtime.cancel(operation_id)
    assert capture.stop_calls == []
    capture.allow_start.set()
    join(runtime)
    event = runtime.poll()
    assert event and event.kind is SpeechRecognitionEventKind.CANCELLED
    assert capture.stop_calls and capture.stop_calls == [runtime._worker.ident]
    assert caller not in capture.stop_calls
    assert turns.snapshot().state is AudioTurnState.IDLE


def test_cancel_while_read_waits_and_cleanup_failure_preserve_terminal() -> None:
    capture = GatedCapture(cleanup_fails=True)
    capture.allow_start.set()
    runtime = SpeechInputRuntime(
        capture, FakeSpeechRecognizer(), AudioTurnCoordinator()
    )
    operation_id = runtime.start()
    assert capture.read_entered.wait(1)
    assert runtime.cancel(operation_id)
    capture.allow_read.set()
    join(runtime)
    event = runtime.poll()
    assert event and event.kind is SpeechRecognitionEventKind.CANCELLED
    assert not runtime.active


@pytest.mark.parametrize("first", ["cancel", "finalize"])
def test_cancel_and_finalize_are_first_cause_wins(first: str) -> None:
    capture = GatedCapture()
    turns = AudioTurnCoordinator()
    runtime = SpeechInputRuntime(
        capture,
        FakeSpeechRecognizer(
            final=RecognitionUpdate(RecognitionUpdateKind.FINAL, text="final")
        ),
        turns,
    )
    operation_id = runtime.start()
    assert capture.start_entered.wait(1)
    actions = {
        "cancel": lambda: runtime.cancel(operation_id),
        "finalize": lambda: runtime.finalize(operation_id),
    }
    second = "finalize" if first == "cancel" else "cancel"
    assert actions[first]()
    assert not actions[second]()
    capture.allow_start.set()
    join(runtime)
    event = runtime.poll()
    assert event
    expected = (
        SpeechRecognitionEventKind.CANCELLED
        if first == "cancel"
        else SpeechRecognitionEventKind.FINAL
    )
    assert event.kind is expected
    assert turns.snapshot().state is AudioTurnState.IDLE


def test_close_is_bounded_when_capture_start_is_stuck() -> None:
    capture = GatedCapture()
    runtime = SpeechInputRuntime(
        capture,
        FakeSpeechRecognizer(),
        AudioTurnCoordinator(),
        close_join_timeout_seconds=0.01,
    )
    runtime.start()
    assert capture.start_entered.wait(1)
    closed = threading.Event()

    def close() -> None:
        runtime.close()
        closed.set()

    closer = threading.Thread(target=close)
    closer.start()
    assert closed.wait(1)
    closer.join(1)
    assert runtime.state is SpeechInputState.CLOSED
    capture.allow_start.set()
    join(runtime)
    event = runtime.poll()
    assert event and event.kind is SpeechRecognitionEventKind.CANCELLED


class CountingTurns(AudioTurnCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.effective_releases = 0

    def release(self, lease):  # type: ignore[no-untyped-def]
        released = super().release(lease)
        self.effective_releases += int(released)
        return released


def assert_one_terminal(
    runtime: SpeechInputRuntime,
    turns: CountingTurns,
    expected: SpeechRecognitionEventKind,
    reason: str,
    releases: int = 1,
) -> None:
    join(runtime)
    event = runtime.poll()
    assert event is not None
    assert event.kind is expected
    assert event.safe_reason == reason
    assert runtime.poll() is None
    assert runtime.state is SpeechInputState.IDLE
    assert not runtime.active
    assert turns.snapshot().state is AudioTurnState.IDLE
    assert turns.snapshot().lease is None
    assert turns.effective_releases == releases
    worker = runtime._worker
    assert worker is not None and not worker.is_alive()


def test_cancel_before_capture_start_is_first_cause_and_released_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = FakePcmCapture()
    turns = CountingTurns()
    runtime = SpeechInputRuntime(capture, FakeSpeechRecognizer(), turns)
    entered, proceed = threading.Event(), threading.Event()
    original = runtime._run

    def gated(operation_id: str) -> None:
        entered.set()
        assert proceed.wait(1)
        original(operation_id)

    monkeypatch.setattr(runtime, "_run", gated)
    operation_id = runtime.start()
    assert entered.wait(1)
    assert runtime.cancel(operation_id)
    assert not runtime.finalize(operation_id)
    assert not capture.active
    proceed.set()
    assert_one_terminal(
        runtime, turns, SpeechRecognitionEventKind.CANCELLED, "cancelled"
    )
    assert not capture.active


def test_cancel_wins_timeout_race() -> None:
    capture = GatedCapture()
    turns = CountingTurns()
    runtime = SpeechInputRuntime(capture, FakeSpeechRecognizer(), turns)
    operation_id = runtime.start()
    assert capture.start_entered.wait(1)
    assert runtime.cancel(operation_id)
    capture.allow_start.set()
    assert_one_terminal(
        runtime, turns, SpeechRecognitionEventKind.CANCELLED, "cancelled"
    )


def test_timeout_wins_late_cancel() -> None:
    turns = CountingTurns()
    clock_values = iter((0.0, 2.0))
    runtime = SpeechInputRuntime(
        FakePcmCapture(),
        FakeSpeechRecognizer(),
        turns,
        maximum_duration_seconds=1,
        clock=lambda: next(clock_values, 2.0),
    )
    operation_id = runtime.start()
    assert_one_terminal(
        runtime, turns, SpeechRecognitionEventKind.TIMEOUT, "maximum_duration"
    )
    assert not runtime.cancel(operation_id)


@pytest.mark.parametrize(
    ("first", "expected", "reason"),
    [
        ("cancel", SpeechRecognitionEventKind.CANCELLED, "cancelled"),
        ("eof", SpeechRecognitionEventKind.FAILED, "capture_eof_unexpected"),
    ],
)
def test_cancel_and_eof_first_cause_matrix(
    first: str, expected: SpeechRecognitionEventKind, reason: str
) -> None:
    capture = GatedCapture()
    capture.allow_start.set()
    turns = CountingTurns()
    runtime = SpeechInputRuntime(capture, FakeSpeechRecognizer(), turns)
    operation_id = runtime.start()
    assert capture.read_entered.wait(1)
    if first == "cancel":
        assert runtime.cancel(operation_id)
    capture.read_chunk = lambda: PcmReadResult(PcmReadKind.EOF)  # type: ignore[method-assign]
    capture.allow_read.set()
    assert_one_terminal(runtime, turns, expected, reason)
    assert not runtime.cancel(operation_id)


class CountingRecognizer(FakeSpeechRecognizer):
    def __init__(self) -> None:
        super().__init__(
            final=RecognitionUpdate(RecognitionUpdateKind.FINAL, text="final")
        )
        self.finalize_calls = 0

    def finalize(self) -> RecognitionUpdate:
        self.finalize_calls += 1
        return super().finalize()


@pytest.mark.parametrize(
    ("first", "expected", "reason", "finalize_calls"),
    [
        ("finalize", SpeechRecognitionEventKind.FINAL, None, 1),
        ("eof", SpeechRecognitionEventKind.FAILED, "capture_eof_unexpected", 0),
    ],
)
def test_finalize_and_eof_first_cause_matrix(
    first: str,
    expected: SpeechRecognitionEventKind,
    reason: str | None,
    finalize_calls: int,
) -> None:
    capture = GatedCapture()
    capture.allow_start.set()
    recognizer = CountingRecognizer()
    turns = CountingTurns()
    runtime = SpeechInputRuntime(capture, recognizer, turns)
    operation_id = runtime.start()
    assert capture.read_entered.wait(1)
    if first == "finalize":
        assert runtime.finalize(operation_id)
    capture.read_chunk = lambda: PcmReadResult(PcmReadKind.EOF)  # type: ignore[method-assign]
    capture.allow_read.set()
    join(runtime)
    event = runtime.poll()
    assert event and event.kind is expected and event.safe_reason == reason
    assert runtime.poll() is None
    assert recognizer.finalize_calls == finalize_calls
    assert turns.effective_releases == 1
    assert turns.snapshot().state is AudioTurnState.IDLE


def test_normal_terminal_survives_cleanup_exception() -> None:
    capture = GatedCapture(cleanup_fails=True)
    capture.allow_start.set()
    capture.read_chunk = lambda: PcmReadResult(PcmReadKind.EOF)  # type: ignore[method-assign]
    turns = CountingTurns()
    runtime = SpeechInputRuntime(capture, FakeSpeechRecognizer(), turns)
    runtime.start()
    assert_one_terminal(
        runtime, turns, SpeechRecognitionEventKind.FAILED, "capture_eof_unexpected"
    )


def test_stale_commit_from_a_cannot_affect_b_or_release_its_lease() -> None:
    turns = CountingTurns()
    first = SpeechInputRuntime(
        FakePcmCapture((PcmReadResult(PcmReadKind.EOF),)),
        FakeSpeechRecognizer(),
        turns,
    )
    operation_a = first.start()
    assert_one_terminal(
        first, turns, SpeechRecognitionEventKind.FAILED, "capture_eof_unexpected"
    )
    capture_b = GatedCapture()
    runtime_b = SpeechInputRuntime(capture_b, FakeSpeechRecognizer(), turns)
    operation_b = runtime_b.start()
    assert capture_b.start_entered.wait(1)
    lease_b = turns.snapshot().lease
    assert not first._commit_terminal(
        operation_a, SpeechRecognitionEventKind.FINAL, "stale", None
    )
    assert operation_a != operation_b
    assert turns.snapshot().lease == lease_b
    assert runtime_b.cancel(operation_b)
    capture_b.allow_start.set()
    assert_one_terminal(
        runtime_b, turns, SpeechRecognitionEventKind.CANCELLED, "cancelled", 2
    )
    assert turns.effective_releases == 2


class BlockingReadCapture(FakePcmCapture):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def read_chunk(self) -> PcmReadResult:
        self.entered.set()
        assert self.release.wait(1)
        return PcmReadResult(PcmReadKind.TIMEOUT)


class SpyContexts(SessionContextStore):
    def __init__(self) -> None:
        super().__init__()
        self.append_calls = 0

    def append(self, session_id, message):  # type: ignore[no-untyped-def]
        self.append_calls += 1
        return super().append(session_id, message)


class SpyIntelligence:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return IntelligenceResponse(
            IntelligenceDecision(DecisionType.RESPOND_ONLY, "texto"),
            "spy",
            "spy",
        )


def test_integrated_voice_stop_matrix_is_local_correlated_and_one_shot() -> None:
    positives = ("stop", "para", "detente", "detén", " STOP ", "DeTéN!", " para. ")
    negatives = ("stop...", "no te detengas", "puedes parar", "para para")
    for index, text in enumerate(positives):
        turns = CountingTurns()
        capture = BlockingReadCapture()
        runtime = SpeechInputRuntime(
            capture,
            FakeSpeechRecognizer(
                final=RecognitionUpdate(RecognitionUpdateKind.FINAL, text=text)
            ),
            turns,
        )
        catalog = create_default_catalog()
        robot = SimulatedRobotAdapter()
        robot.connect()
        robot.read_events()
        runner = CapabilityRunner(catalog, robot)
        contexts = SpyContexts()
        intelligence = SpyIntelligence()
        conversation = ConversationOrchestrator(
            intelligence=intelligence,
            catalog=catalog,
            runner=runner,
            contexts=contexts,
        )
        raw_output = FakeSpeechOutput()
        output = GuardedSpeechOutput(raw_output, turns)
        coordinator = SpeechInputCoordinator(
            runtime,
            stop_router=LocalStopRouter(),
            speech_output=output,
            runner=runner,
            conversation=conversation,
            session_id=f"voice-stop-{index}",
        )
        operation_id = coordinator.start()
        assert capture.entered.wait(1)
        assert runtime.finalize(operation_id)
        capture.release.set()
        join(runtime)
        assert runtime.state is SpeechInputState.IDLE
        assert turns.snapshot().state is AudioTurnState.IDLE
        output_id = output.start("active output")
        dispatch = coordinator.poll()
        assert dispatch and dispatch.event.operation_id == operation_id
        assert dispatch.event.kind is SpeechRecognitionEventKind.FINAL
        assert dispatch.stop and dispatch.stop.matched
        assert dispatch.stop.tts_cancelled
        assert dispatch.stop.robot_result and dispatch.stop.robot_result.succeeded
        assert [command.action for command in robot.commands] == ["stop"]
        assert not runtime.cancel(operation_id)
        assert not raw_output.complete()
        assert output.poll() is not None
        raw_output._on_terminal(output_id)
        assert coordinator.poll() is None
        assert contexts.append_calls == 0
        assert intelligence.calls == 0
        assert turns.effective_releases == 2
        assert turns.snapshot().state is AudioTurnState.IDLE
        assert runtime.poll() is None

    router = LocalStopRouter()
    assert all(not router.matches(text) for text in negatives)
    assert not router.matches("par")
    partial = SpeechRecognitionEvent(
        "partial-operation", SpeechRecognitionEventKind.PARTIAL, text="stop"
    )
    assert partial.kind is SpeechRecognitionEventKind.PARTIAL
