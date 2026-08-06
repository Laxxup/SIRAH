"""SIRAH — Sistema Inteligente Robotico de Asistencia Humana.

Modular conversational robotic agent built on SIRAH Cortex.
"""

from __future__ import annotations

from sirah.action import ActionRunner, CapabilityCatalog, CapabilityPolicy
from sirah.core import ComponentRegistry, ConversationContext, SirahOrchestrator
from sirah.errors import *  # noqa: F403
from sirah.factory import SystemAssembly, SystemProfile, build_system
from sirah.intelligence import IntelligencePort
from sirah.perception import PerceptionPort
from sirah.social import (
    InteractionMemory,
    SituationalCoordinator,
    evaluate_initiative,
)
from sirah.types import *  # noqa: F403
from sirah.voice import SpeechInputPort, SpeechOutputPort

__all__ = [
    "build_system",
    "SystemProfile",
    "SystemAssembly",
    "SirahOrchestrator",
    "ConversationContext",
    "ComponentRegistry",
    "IntelligencePort",
    "PerceptionPort",
    "SpeechInputPort",
    "SpeechOutputPort",
    "CapabilityCatalog",
    "CapabilityPolicy",
    "ActionRunner",
    "InteractionMemory",
    "evaluate_initiative",
    "SituationalCoordinator",
]
