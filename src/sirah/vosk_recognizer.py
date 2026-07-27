"""Reconocedor Vosk local con import tardío y acumulación acotada."""

from __future__ import annotations

import importlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SpeechInputError
from .speech_input import RecognitionUpdate, RecognitionUpdateKind


@dataclass(frozen=True, slots=True)
class VoskRecognizerConfig:
    model_path: Path
    sample_rate: int = 16000
    max_partial_chars: int = 256
    max_final_chars: int = 4096
    max_segments: int = 32

    def __post_init__(self) -> None:
        for value in (
            self.sample_rate,
            self.max_partial_chars,
            self.max_final_chars,
            self.max_segments,
        ):
            if type(value) is not int or value <= 0:
                raise ValueError("Los límites Vosk deben ser enteros positivos.")


class VoskSpeechRecognizer:
    def __init__(self, config: VoskRecognizerConfig) -> None:
        self._config = config
        self._module: Any = None
        self._model: Any = None
        self._recognizer: Any = None
        self._segments: list[str] = []
        self._failure: RecognitionUpdate | None = None
        self._final: RecognitionUpdate | None = None
        self._ready = False
        self._closed = False
        self._available = self._probe()

    def _probe(self) -> bool:
        try:
            self._module = importlib.import_module("vosk")
        except (ImportError, OSError):
            return False
        return self._config.model_path.is_dir() and os.access(
            self._config.model_path, os.R_OK | os.X_OK
        )

    @property
    def available(self) -> bool:
        return self._available and not self._closed

    def reset(self) -> None:
        if self._closed:
            raise SpeechInputError("recognizer_closed")
        if not self._available:
            raise SpeechInputError("vosk_unavailable")
        try:
            if self._model is None:
                self._model = self._module.Model(str(self._config.model_path))
            self._recognizer = self._module.KaldiRecognizer(
                self._model, self._config.sample_rate
            )
        except Exception as error:
            raise SpeechInputError("vosk_initialization_failed") from error
        self._segments = []
        self._failure = self._final = None
        self._ready = True

    def accept_pcm(self, chunk: bytes) -> RecognitionUpdate | None:
        if not self._ready or self._final is not None:
            raise SpeechInputError("recognizer_lifecycle_invalid")
        if self._failure is not None:
            return self._failure
        try:
            complete = self._recognizer.AcceptWaveform(chunk)
            raw = self._recognizer.Result() if complete else self._recognizer.PartialResult()
            parsed = self._parse(raw)
            if complete:
                text = self._string(parsed, "text")
                if text:
                    self._append_segment(text)
                return self._failure
            partial = self._string(parsed, "partial")
            if len(partial) > self._config.max_partial_chars:
                return self._fail("vosk_partial_limit")
            return (
                RecognitionUpdate(RecognitionUpdateKind.PARTIAL, text=partial)
                if partial
                else None
            )
        except Exception:
            return self._fail("vosk_processing_failed")

    def finalize(self) -> RecognitionUpdate:
        if self._final is not None:
            return self._final
        if not self._ready:
            raise SpeechInputError("recognizer_lifecycle_invalid")
        if self._failure is not None:
            self._final = self._failure
            return self._final
        try:
            parsed = self._parse(self._recognizer.FinalResult())
            text = self._string(parsed, "text")
            if text:
                self._append_segment(text)
        except Exception:
            self._fail("vosk_finalization_failed")
        if self._failure is not None:
            self._final = self._failure
        else:
            combined = " ".join(" ".join(self._segments).split())
            if len(combined) > self._config.max_final_chars:
                self._final = self._fail("vosk_final_limit")
            elif combined:
                self._final = RecognitionUpdate(RecognitionUpdateKind.FINAL, text=combined)
            else:
                self._final = RecognitionUpdate(RecognitionUpdateKind.NO_SPEECH)
        return self._final

    def _append_segment(self, text: str) -> None:
        if len(self._segments) >= self._config.max_segments:
            self._fail("vosk_segment_limit")
            return
        prospective = sum(len(item) for item in self._segments) + len(text)
        if prospective + len(self._segments) > self._config.max_final_chars:
            self._fail("vosk_final_limit")
            return
        self._segments.append(text)

    def _fail(self, reason: str) -> RecognitionUpdate:
        if self._failure is None:
            self._failure = RecognitionUpdate(
                RecognitionUpdateKind.FAILURE, safe_reason=reason
            )
        return self._failure

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise SpeechInputError("vosk_json_root_invalid")
        return value

    @staticmethod
    def _string(value: dict[str, Any], key: str) -> str:
        field = value.get(key, "")
        if not isinstance(field, str):
            raise SpeechInputError("vosk_json_field_invalid")
        alternatives = value.get("alternatives")
        if alternatives is not None and (
            not isinstance(alternatives, list)
            or any(not isinstance(item, dict) for item in alternatives)
        ):
            raise SpeechInputError("vosk_json_alternatives_invalid")
        confidence = value.get("confidence")
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise SpeechInputError("vosk_json_confidence_invalid")
        return field

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._recognizer = self._model = self._module = None
