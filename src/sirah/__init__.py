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
from .errors import (
    CapabilityExecutionError,
    CapabilityRejectedError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceUnavailableError,
    InvalidIntelligenceResponseError,
    SirahApplicationError,
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
    "IntelligenceRateLimitError",
    "IntelligenceTimeoutError",
    "IntelligenceUnavailableError",
    "InvalidIntelligenceResponseError",
    "ParameterDefinition",
    "SirahApplicationError",
    "create_default_catalog",
]
