from __future__ import annotations

from pathlib import Path

import pytest

from sirah.errors import SpeechInputError
from sirah.speech_input import RecognitionUpdateKind
from sirah.vosk_recognizer import VoskRecognizerConfig, VoskSpeechRecognizer


class FakeKaldi:
    def __init__(self, results: list[tuple[bool, str]], final: str) -> None:
        self.results = iter(results)
        self.final = final
        self.current = ""

    def AcceptWaveform(self, chunk: bytes) -> bool:
        complete, self.current = next(self.results)
        return complete

    def Result(self) -> str:
        return self.current

    def PartialResult(self) -> str:
        return self.current

    def FinalResult(self) -> str:
        return self.final


class FakeVosk:
    def __init__(self, kaldi: FakeKaldi) -> None:
        self.kaldi = kaldi

    def Model(self, path: str) -> object:
        return object()

    def KaldiRecognizer(self, model: object, rate: int) -> FakeKaldi:
        return self.kaldi


def configured(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kaldi: FakeKaldi,
    **limits: int,
) -> VoskSpeechRecognizer:
    monkeypatch.setattr(
        "sirah.vosk_recognizer.importlib.import_module",
        lambda name: FakeVosk(kaldi),
    )
    return VoskSpeechRecognizer(VoskRecognizerConfig(tmp_path, **limits))


def test_internal_segments_produce_only_one_final(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recognizer = configured(
        monkeypatch,
        tmp_path,
        FakeKaldi(
            [(True, '{"text":"uno"}'), (True, '{"text":"dos"}')],
            '{"text":"tres"}',
        ),
    )
    recognizer.reset()
    assert recognizer.accept_pcm(b"\0\0") is None
    assert recognizer.accept_pcm(b"\0\0") is None
    final = recognizer.finalize()
    assert final.kind is RecognitionUpdateKind.FINAL
    assert final.text == "uno dos tres"
    assert recognizer.finalize() is final
    with pytest.raises(SpeechInputError):
        recognizer.accept_pcm(b"\0\0")


@pytest.mark.parametrize("root", ["[]", "null", "1"])
def test_invalid_json_roots_are_terminal_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: str
) -> None:
    recognizer = configured(
        monkeypatch, tmp_path, FakeKaldi([(False, root)], '{"text":""}')
    )
    recognizer.reset()
    update = recognizer.accept_pcm(b"\0\0")
    assert update and update.kind is RecognitionUpdateKind.FAILURE
    assert update.text is None


@pytest.mark.parametrize(
    "confidence", ["true", '"bad"', "NaN", "Infinity", "+Infinity", "-Infinity", "-1", "2"]
)
def test_invalid_confidence_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, confidence: str
) -> None:
    raw = '{"partial":"x","confidence":' + confidence + "}"
    recognizer = configured(
        monkeypatch, tmp_path, FakeKaldi([(False, raw)], '{"text":""}')
    )
    recognizer.reset()
    assert recognizer.accept_pcm(b"\0\0").kind is RecognitionUpdateKind.FAILURE  # type: ignore[union-attr]


def test_segment_and_text_limits_fail_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recognizer = configured(
        monkeypatch,
        tmp_path,
        FakeKaldi(
            [(True, '{"text":"one"}'), (True, '{"text":"two"}')],
            '{"text":"three"}',
        ),
        max_segments=1,
        max_final_chars=8,
    )
    recognizer.reset()
    recognizer.accept_pcm(b"\0\0")
    failure = recognizer.accept_pcm(b"\0\0")
    assert failure and failure.kind is RecognitionUpdateKind.FAILURE
    assert failure.safe_reason == "vosk_segment_limit"
    assert recognizer.finalize() is failure


def test_reset_after_failure_creates_clean_operation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recognizer = configured(
        monkeypatch, tmp_path, FakeKaldi([(False, "[]")], '{"text":""}')
    )
    recognizer.reset()
    assert recognizer.accept_pcm(b"\0\0").kind is RecognitionUpdateKind.FAILURE  # type: ignore[union-attr]
    recognizer.reset()
    assert recognizer.finalize().kind is RecognitionUpdateKind.NO_SPEECH
    recognizer.close()
    recognizer.close()
    with pytest.raises(SpeechInputError):
        recognizer.reset()


@pytest.mark.parametrize(
    "raw",
    [
        '{"partial":1}',
        '{"partial":"x","alternatives":{}}',
        '{"partial":"x","alternatives":[1]}',
        '{"partial":"x","confidence":false}',
        '{"partial":"x","confidence":-Infinity}',
    ],
)
def test_defensive_partial_fields_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str
) -> None:
    recognizer = configured(
        monkeypatch, tmp_path, FakeKaldi([(False, raw)], '{"text":""}')
    )
    recognizer.reset()
    result = recognizer.accept_pcm(b"\0\0")
    assert result and result.kind is RecognitionUpdateKind.FAILURE


@pytest.mark.parametrize(
    "raw",
    [
        '{"text":1}',
        '{"text":"x","alternatives":{}}',
        '{"text":"x","alternatives":[null]}',
        '{"text":"x","confidence":1.01}',
    ],
)
def test_defensive_final_fields_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, raw: str
) -> None:
    recognizer = configured(monkeypatch, tmp_path, FakeKaldi([], raw))
    recognizer.reset()
    result = recognizer.finalize()
    assert result.kind is RecognitionUpdateKind.FAILURE
    assert recognizer.finalize() is result


def test_partial_and_final_limits_are_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recognizer = configured(
        monkeypatch,
        tmp_path,
        FakeKaldi([(False, '{"partial":"12345"}')], '{"text":""}'),
        max_partial_chars=4,
        max_final_chars=20,
    )
    recognizer.reset()
    result = recognizer.accept_pcm(b"\0\0")
    assert result and result.safe_reason == "vosk_partial_limit"

    monkeypatch.undo()
    recognizer = configured(
        monkeypatch,
        tmp_path,
        FakeKaldi([(True, '{"text":"1234"}')], '{"text":"5678"}'),
        max_segments=3,
        max_final_chars=8,
    )
    recognizer.reset()
    recognizer.accept_pcm(b"\0\0")
    result = recognizer.finalize()
    assert result.kind is RecognitionUpdateKind.FAILURE
    assert result.safe_reason == "vosk_final_limit"


@pytest.mark.parametrize("confidence", ["0", "1", "0.5"])
def test_confidence_boundaries_are_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, confidence: str
) -> None:
    recognizer = configured(
        monkeypatch,
        tmp_path,
        FakeKaldi(
            [(False, '{"partial":"ok","confidence":' + confidence + "}")],
            '{"text":""}',
        ),
    )
    recognizer.reset()
    update = recognizer.accept_pcm(b"\0\0")
    assert update and update.kind is RecognitionUpdateKind.PARTIAL
    assert update.text == "ok"
