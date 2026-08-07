"""Personality data contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonalityPrompt:
    """Composed system prompt derived from personality files.

    Sections are stored individually so callers can inspect or recompose them.
    """

    base_prompt: str
    identity: str = ""
    role: str = ""
    personality: str = ""
    behavior: str = ""
    speech_style: str = ""
    boundaries: str = ""
    source_dir: str = ""
    warnings: tuple[str, ...] = ()
    missing_optional: tuple[str, ...] = ()
