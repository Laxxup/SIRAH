"""Fachada pública inicial de SIRAH."""

from .capabilities import (
    CapabilityCatalog,
    CapabilityDefinition,
    CapabilityPolicy,
    CapabilityRequest,
    ParameterDefinition,
)
from .cortex_integration import (
    CapabilityExecutionResult,
    CapabilityRunner,
    create_default_catalog,
)
from .context import ConversationMessage, PresentContext, SessionContextStore
from .conversation import ConversationOrchestrator, ConversationResult
from .errors import (
    CapabilityExecutionError,
    CapabilityRejectedError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
    InvalidIntelligenceResponseError,
    SirahApplicationError,
)
from .intelligence import (
    DecisionType,
    IntelligenceDecision,
    IntelligencePort,
    IntelligenceRequest,
    IntelligenceResponse,
)
from .system import (
    ComponentId,
    ComponentKind,
    ComponentRegistry,
    ComponentState,
    ComponentStatus,
    PresentSystem,
    SystemSnapshot,
)
from .interaction import InitiativeAction, InitiativeDecision, InteractionMemory, evaluate_initiative
from .situational_runtime import SituationalCoordinator
from .speech import SpeechOutputPort
from .audio_turn import (
    AudioTurnCoordinator,
    AudioTurnDirection,
    AudioTurnLease,
    AudioTurnState,
)
from .speech_input import (
    PcmCapturePort,
    PcmReadKind,
    PcmReadResult,
    RecognitionUpdate,
    RecognitionUpdateKind,
    SpeechInputState,
    SpeechRecognitionEvent,
    SpeechRecognitionEventKind,
    SpeechRecognizerPort,
)

__all__ = [
    "CapabilityCatalog",
    "CapabilityDefinition",
    "CapabilityExecutionError",
    "CapabilityExecutionResult",
    "CapabilityPolicy",
    "CapabilityRejectedError",
    "CapabilityRequest",
    "CapabilityRunner",
    "ComponentId",
    "ComponentKind",
    "ComponentRegistry",
    "ComponentState",
    "ComponentStatus",
    "ConversationMessage",
    "ConversationOrchestrator",
    "ConversationResult",
    "DecisionType",
    "IntelligenceDecision",
    "IntelligencePort",
    "IntelligenceRateLimitError",
    "IntelligenceRequest",
    "IntelligenceResponse",
    "IntelligenceTimeoutError",
    "IntelligenceUnavailableError",
    "InvalidIntelligenceResponseError",
    "InitiativeAction",
    "InitiativeDecision",
    "InteractionMemory",
    "ParameterDefinition",
    "PresentContext",
    "PresentSystem",
    "SessionContextStore",
    "SituationalCoordinator",
    "SpeechOutputPort",
    "AudioTurnCoordinator",
    "AudioTurnDirection",
    "AudioTurnLease",
    "AudioTurnState",
    "PcmCapturePort",
    "PcmReadKind",
    "PcmReadResult",
    "RecognitionUpdate",
    "RecognitionUpdateKind",
    "SpeechInputState",
    "SpeechRecognitionEvent",
    "SpeechRecognitionEventKind",
    "SpeechRecognizerPort",
    "SirahApplicationError",
    "SystemSnapshot",
    "evaluate_initiative",
    "create_default_catalog",
]
