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
    "TTSInvalidAudioError",
    "TTSTimeoutError",
    "SpeechInputError",
    "SpeechRecognitionError",
    "SpeechRecognitionTimeoutError",
    "AudioCaptureError",
    "AudioFormatError",
    "AudioTurnBusyError",
    "RuntimeAccessDeniedError",
    "RuntimeAssemblyAccessError",
    "RuntimeConfigurationError",
    "PersonalityConfigurationError",
    "DeviceNotAllowedError",
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


class TTSInvalidAudioError(SpeechError):
    """TTS service returned invalid or unexpected audio data."""


class TTSTimeoutError(SpeechUnavailableError):
    """TTS request exceeded the configured deadline."""


class SpeechInputError(SpeechError):
    """STT capture or recognition failure."""


class SpeechRecognitionError(SpeechInputError):
    """The speech recognizer could not produce a result."""


class SpeechRecognitionTimeoutError(SpeechRecognitionError):
    """The speech recognizer exceeded its per-turn deadline."""


class AudioCaptureError(SpeechInputError):
    """The configured server-side capture process failed."""


class AudioFormatError(SpeechInputError):
    """Captured PCM or WAV does not match the runtime format."""


class AudioTurnBusyError(SpeechError):
    """Audio turn lease is held by another party."""


class RuntimeAccessDeniedError(SirahRecoverableError):
    """Runtime client attempted an unauthorised request."""


class RuntimeAssemblyAccessError(SirahRecoverableError):
    """A caller outside the runtime attempted to assemble the system."""


class RuntimeConfigurationError(SirahFatalError):
    """Server-only runtime configuration is missing or invalid."""


class PersonalityConfigurationError(RuntimeConfigurationError):
    """Personality configuration directory or files are missing or invalid."""


class DeviceNotAllowedError(SirahRecoverableError):
    """Runtime selected a device outside its configured allowlist."""


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
