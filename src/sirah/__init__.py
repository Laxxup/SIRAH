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
    "ParameterDefinition",
    "PresentContext",
    "PresentSystem",
    "SessionContextStore",
    "SirahApplicationError",
    "SystemSnapshot",
    "create_default_catalog",
]
