"""SIRAH — Sistema Inteligente Robotico de Asistencia Humana.

Modular conversational robotic agent built on SIRAH Cortex.
"""

from __future__ import annotations

from sirah.errors import *
from sirah.types import *

from sirah.core import SirahOrchestrator, ConversationContext, ComponentRegistry
from sirah.intelligence import IntelligencePort
from sirah.perception import PerceptionPort
from sirah.voice import SpeechInputPort, SpeechOutputPort
from sirah.action import CapabilityCatalog, CapabilityPolicy, ActionRunner
from sirah.social import (
    InteractionMemory,
    evaluate_initiative,
    SituationalCoordinator,
)
from sirah.factory import SystemProfile, build_system, SystemAssembly

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
