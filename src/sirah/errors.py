"""SIRAH typed error hierarchy."""

from __future__ import annotations

__all__ = [
    "SirahError",
    "SirahFatalError",
    "SirahRecoverableError",
    "BridgeError",
    "BridgeConnectionError",
    "BridgeTimeoutError",
    "IntelligenceError",
    "IntelligenceUnavailableError",
    "IntelligenceTimeoutError",
    "IntelligenceRateLimitError",
    "InvalidIntelligenceResponseError",
    "PerceptionError",
    "PerceptionUnavailableError",
    "SpeechError",
    "SpeechBusyError",
    "SpeechUnavailableError",
    "SpeechInputError",
    "AudioTurnBusyError",
    "ActionError",
    "CapabilityRejectedError",
    "CapabilityExecutionError",
    "CapabilityNotFoundError",
    "SituationalError",
]


class SirahError(Exception):
    """Base for all SIRAH exceptions."""


class SirahFatalError(SirahError):
    """Non-recoverable error that should halt the system."""


class SirahRecoverableError(SirahError):
    """Error that may be retried or degraded gracefully."""


class BridgeError(SirahError):
    """Communication error between laptop and edge device."""


class BridgeConnectionError(BridgeError):
    """Cannot establish or maintain connection to edge."""


class BridgeTimeoutError(BridgeError):
    """Edge operation timed out."""


class IntelligenceError(SirahRecoverableError):
    """LLM reasoning failure."""


class IntelligenceUnavailableError(IntelligenceError):
    """LLM service is unreachable."""


class IntelligenceTimeoutError(IntelligenceError):
    """LLM request exceeded deadline."""


class IntelligenceRateLimitError(IntelligenceError):
    """LLM rate limit hit."""


class InvalidIntelligenceResponseError(IntelligenceError):
    """LLM returned malformed or unparseable output."""


class PerceptionError(SirahRecoverableError):
    """Perception pipeline failure."""


class PerceptionUnavailableError(PerceptionError):
    """Camera or sensor unavailable."""


class SpeechError(SirahRecoverableError):
    """TTS or STT operation failure."""


class SpeechBusyError(SpeechError):
    """Speech output is in use and cannot accept a new request."""


class SpeechUnavailableError(SpeechError):
    """Speech subsystem is not available."""


class SpeechInputError(SpeechError):
    """STT capture or recognition failure."""


class AudioTurnBusyError(SpeechError):
    """Audio turn lease is held by another party."""


class ActionError(SirahRecoverableError):
    """Robot action pipeline failure."""


class CapabilityRejectedError(ActionError):
    """Policy denied the requested capability."""


class CapabilityExecutionError(ActionError):
    """Capability execution failed in Cortex or RobotPort."""


class CapabilityNotFoundError(ActionError):
    """Requested capability is not registered."""


class SituationalError(SirahError):
    """Situational coordinator error."""
