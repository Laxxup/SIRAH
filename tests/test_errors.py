"""Test error hierarchy."""

from __future__ import annotations

from sirah.errors import (
    SirahError,
    SirahFatalError,
    SirahRecoverableError,
    BridgeError,
    BridgeConnectionError,
    BridgeTimeoutError,
    IntelligenceError,
    IntelligenceUnavailableError,
    IntelligenceTimeoutError,
    IntelligenceRateLimitError,
    InvalidIntelligenceResponseError,
    PerceptionError,
    PerceptionUnavailableError,
    SpeechError,
    SpeechBusyError,
    SpeechUnavailableError,
    SpeechInputError,
    AudioTurnBusyError,
    ActionError,
    CapabilityRejectedError,
    CapabilityExecutionError,
    CapabilityNotFoundError,
    SituationalError,
)


def test_sirah_error_base() -> None:
    assert issubclass(SirahError, Exception)


def test_fatal_is_sirah() -> None:
    assert issubclass(SirahFatalError, SirahError)


def test_recoverable_is_sirah() -> None:
    assert issubclass(SirahRecoverableError, SirahError)


def test_intelligence_is_recoverable() -> None:
    assert issubclass(IntelligenceError, SirahRecoverableError)
    assert issubclass(IntelligenceUnavailableError, IntelligenceError)
    assert issubclass(IntelligenceTimeoutError, IntelligenceError)
    assert issubclass(IntelligenceRateLimitError, IntelligenceError)
    assert issubclass(InvalidIntelligenceResponseError, IntelligenceError)


def test_perception_is_recoverable() -> None:
    assert issubclass(PerceptionError, SirahRecoverableError)
    assert issubclass(PerceptionUnavailableError, PerceptionError)


def test_speech_is_recoverable() -> None:
    assert issubclass(SpeechError, SirahRecoverableError)
    assert issubclass(SpeechBusyError, SpeechError)
    assert issubclass(SpeechUnavailableError, SpeechError)
    assert issubclass(SpeechInputError, SpeechError)
    assert issubclass(AudioTurnBusyError, SpeechError)


def test_action_is_recoverable() -> None:
    assert issubclass(ActionError, SirahRecoverableError)
    assert issubclass(CapabilityRejectedError, ActionError)
    assert issubclass(CapabilityExecutionError, ActionError)
    assert issubclass(CapabilityNotFoundError, ActionError)


def test_bridge_is_sirah() -> None:
    assert issubclass(BridgeError, SirahError)
    assert issubclass(BridgeConnectionError, BridgeError)
    assert issubclass(BridgeTimeoutError, BridgeError)


def test_situational_is_sirah() -> None:
    assert issubclass(SituationalError, SirahError)


def test_error_str() -> None:
    e = CapabilityExecutionError("test reason")
    assert str(e) == "test reason"
    assert isinstance(e, ActionError)
    assert isinstance(e, SirahError)
    assert isinstance(e, Exception)
