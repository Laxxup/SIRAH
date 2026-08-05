"""Intelligence layer — LLM reasoning contracts and adapters."""

from __future__ import annotations

__all__ = [
    "IntelligencePort",
    "GroqIntelligence",
    "OllamaIntelligence",
    "FakeIntelligence",
    "LaboratoryIntelligence",
]

from sirah.intelligence.port import IntelligencePort
from sirah.intelligence.groq_adapter import GroqIntelligence
from sirah.intelligence.ollama_adapter import OllamaIntelligence
from sirah.intelligence.fake_adapter import FakeIntelligence
from sirah.intelligence.demo_adapter import LaboratoryIntelligence
