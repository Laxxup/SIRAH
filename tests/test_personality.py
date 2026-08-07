"""Tests for PersonalityLoader and PersonalityPrompt composition."""

from __future__ import annotations

from pathlib import Path

import pytest

from sirah.errors import PersonalityConfigurationError
from sirah.personality import PersonalityLoader
from sirah.personality.loader import MAX_FILE_BYTES


@pytest.fixture
def personality_dir(tmp_path: Path) -> Path:
    """Create a valid personality directory with all files."""
    files = {
        "identity.md": "# Identity\nYou are SIRAH.",
        "role.md": "# Role\nYou are the robot's assistant.",
        "personality.md": "# Personality\nCalm, intelligent, kind.",
        "behavior.md": "# Behavior\nBe honest about sensors.",
        "speech_style.md": "# Speech Style\nShort sentences.",
        "boundaries.md": "# Boundaries\nNo direct hardware control.",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


@pytest.fixture
def loader(personality_dir: Path) -> PersonalityLoader:
    return PersonalityLoader(personality_dir)


class TestPersonalityLoaderLoad:
    def test_load_all_files(self, loader: PersonalityLoader) -> None:
        prompt = loader.load()
        assert "IDENTITY" in prompt.base_prompt
        assert "You are SIRAH." in prompt.identity
        assert prompt.source_dir == str(loader._dir)
        assert prompt.missing_optional == ()

    def test_composition_order(self, loader: PersonalityLoader) -> None:
        prompt = loader.load()
        base = prompt.base_prompt
        idx_identity = base.index("IDENTITY")
        idx_role = base.index("ROLE")
        idx_personality = base.index("PERSONALITY")
        idx_behavior = base.index("BEHAVIOR")
        idx_style = base.index("SPEECH STYLE")
        idx_boundaries = base.index("BOUNDARIES")
        assert idx_identity < idx_role < idx_personality < idx_behavior < idx_style < idx_boundaries

    def test_sections_stored_individually(self, loader: PersonalityLoader) -> None:
        prompt = loader.load()
        assert prompt.identity == "# Identity\nYou are SIRAH."
        assert prompt.boundaries == "# Boundaries\nNo direct hardware control."

    def test_base_prompt_not_empty(self, loader: PersonalityLoader) -> None:
        prompt = loader.load()
        assert len(prompt.base_prompt) > 100

    def test_load_with_warnings_on_empty_file(self, personality_dir: Path) -> None:
        (personality_dir / "personality.md").write_text("", encoding="utf-8")
        loader = PersonalityLoader(personality_dir)
        prompt = loader.load()
        assert "personality.md" in prompt.warnings[0]
        assert "PERSONALITY" not in prompt.base_prompt


class TestPersonalityLoaderValidation:
    def test_missing_required_file_raises(self, personality_dir: Path) -> None:
        (personality_dir / "identity.md").unlink()
        loader = PersonalityLoader(personality_dir)
        with pytest.raises(PersonalityConfigurationError, match="required personality file missing"):
            loader.load()

    def test_missing_all_required_raises(self, tmp_path: Path) -> None:
        loader = PersonalityLoader(tmp_path)
        with pytest.raises(PersonalityConfigurationError):
            loader.load()

    def test_optional_file_missing_no_crash(self, personality_dir: Path) -> None:
        (personality_dir / "personality.md").unlink()
        (personality_dir / "speech_style.md").unlink()
        loader = PersonalityLoader(personality_dir)
        prompt = loader.load()
        assert "personality.md" in prompt.missing_optional
        assert "speech_style.md" in prompt.missing_optional
        assert "PERSONALITY" not in prompt.base_prompt

    def test_directory_missing_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist"
        loader = PersonalityLoader(missing)
        with pytest.raises(PersonalityConfigurationError, match="does not exist"):
            loader.load()

    def test_validate_returns_problems(self, tmp_path: Path) -> None:
        loader = PersonalityLoader(tmp_path)
        problems = loader.validate()
        assert len(problems) >= 1

    def test_validate_empty_for_valid_dir(self, loader: PersonalityLoader) -> None:
        assert loader.validate() == []


class TestPersonalityLoaderFileConstraints:
    def test_file_too_large_raises(self, personality_dir: Path) -> None:
        big = "x" * (MAX_FILE_BYTES + 10)
        (personality_dir / "identity.md").write_text(big, encoding="utf-8")
        loader = PersonalityLoader(personality_dir)
        with pytest.raises(PersonalityConfigurationError, match="too large"):
            loader.load()

    def test_utf8_content(self, personality_dir: Path) -> None:
        (personality_dir / "identity.md").write_text(
            "# Identity\nSIRAH: cálculo, acción, ñandú.", encoding="utf-8"
        )
        loader = PersonalityLoader(personality_dir)
        prompt = loader.load()
        assert "cálculo" in prompt.identity

    def test_utf8_with_bom_raises_or_reads(self, personality_dir: Path) -> None:
        content = "\ufeff# Identity\nSIRAH."
        (personality_dir / "identity.md").write_text(content, encoding="utf-8-sig")
        loader = PersonalityLoader(personality_dir)
        prompt = loader.load()
        assert "SIRAH" in prompt.identity

    def test_non_utf8_raises(self, personality_dir: Path) -> None:
        (personality_dir / "identity.md").write_bytes(b"\xff\xfe# bad bytes")
        loader = PersonalityLoader(personality_dir)
        with pytest.raises(PersonalityConfigurationError, match="UTF-8"):
            loader.load()


class TestPersonalityLoaderReload:
    def test_reload_refreshes(self, personality_dir: Path) -> None:
        loader = PersonalityLoader(personality_dir)
        first = loader.load()
        (personality_dir / "identity.md").write_text("# Identity\nUPDATED.", encoding="utf-8")
        second = loader.reload()
        assert "UPDATED." in second.identity
        assert first.identity != second.identity


class TestPersonalityDecoupling:
    def test_loader_imports_no_intelligence(self) -> None:
        import sirah.personality as personality_package  # noqa: F401
        src = Path(__file__).parent.parent / "src" / "sirah" / "personality" / "loader.py"
        text = src.read_text(encoding="utf-8")
        assert "IntelligencePort" not in text
        assert "ollama" not in text.lower()
        assert "groq" not in text.lower()

    def test_personality_has_no_hardware_authority(self, loader: PersonalityLoader) -> None:
        prompt = loader.load()
        assert "PWM" not in prompt.base_prompt
        assert "GPIO" not in prompt.base_prompt
        assert "servo angle" not in prompt.base_prompt.lower()

    def test_loader_failure_does_not_touch_hardware(self, tmp_path: Path) -> None:
        loader = PersonalityLoader(tmp_path / "missing")
        with pytest.raises(PersonalityConfigurationError):
            loader.load()
