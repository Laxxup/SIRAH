"""PersonalityLoader — reads personality Markdown files and composes the system prompt."""

from __future__ import annotations

import logging
from pathlib import Path

from sirah.errors import PersonalityConfigurationError
from sirah.personality.models import PersonalityPrompt

logger = logging.getLogger(__name__)

REQUIRED_FILES = ("identity.md", "role.md", "behavior.md", "boundaries.md")
OPTIONAL_FILES = ("personality.md", "speech_style.md")
ALL_FILES = REQUIRED_FILES + OPTIONAL_FILES

COMPOSITION_ORDER = (
    "identity.md",
    "role.md",
    "personality.md",
    "behavior.md",
    "speech_style.md",
    "boundaries.md",
)

MAX_FILE_BYTES = 50_000

_SECTION_TITLES = {
    "identity.md": "IDENTITY",
    "role.md": "ROLE",
    "personality.md": "PERSONALITY",
    "behavior.md": "BEHAVIOR",
    "speech_style.md": "SPEECH STYLE",
    "boundaries.md": "BOUNDARIES",
}


class PersonalityLoader:
    """Read personality Markdown files from a directory and compose the base system prompt."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory).expanduser().resolve()

    def load(self) -> PersonalityPrompt:
        if not self._dir.is_dir():
            raise PersonalityConfigurationError(
                f"personality directory does not exist: {self._dir}"
            )

        files: dict[str, str] = {}
        warnings: list[str] = []
        missing_optional: list[str] = []

        for name in ALL_FILES:
            path = self._dir / name
            if not path.is_file():
                if name in REQUIRED_FILES:
                    raise PersonalityConfigurationError(
                        f"required personality file missing: {path}"
                    )
                missing_optional.append(name)
                continue
            content = self._read_file(path)
            if not content:
                warnings.append(f"personality file empty: {path}")
                continue
            files[name] = content

        sections = self._compose(files)
        return PersonalityPrompt(
            base_prompt=sections["base"],
            identity=sections["identity"],
            role=sections["role"],
            personality=sections["personality"],
            behavior=sections["behavior"],
            speech_style=sections["speech_style"],
            boundaries=sections["boundaries"],
            source_dir=str(self._dir),
            warnings=tuple(warnings),
            missing_optional=tuple(missing_optional),
        )

    def reload(self) -> PersonalityPrompt:
        return self.load()

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self._dir.is_dir():
            problems.append(f"directory does not exist: {self._dir}")
            return problems
        for name in REQUIRED_FILES:
            path = self._dir / name
            if not path.is_file():
                problems.append(f"required file missing: {path}")
        return problems

    def _read_file(self, path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise PersonalityConfigurationError(f"cannot read {path}: {exc}") from exc
        if len(raw) > MAX_FILE_BYTES:
            raise PersonalityConfigurationError(
                f"personality file too large ({len(raw)} bytes > {MAX_FILE_BYTES}): {path}"
            )
        try:
            return raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise PersonalityConfigurationError(
                f"personality file not valid UTF-8: {path}: {exc}"
            ) from exc

    def _compose(self, files: dict[str, str]) -> dict[str, str]:
        sections: dict[str, str] = {
            "base": "",
            "identity": files.get("identity.md", ""),
            "role": files.get("role.md", ""),
            "personality": files.get("personality.md", ""),
            "behavior": files.get("behavior.md", ""),
            "speech_style": files.get("speech_style.md", ""),
            "boundaries": files.get("boundaries.md", ""),
        }
        parts: list[str] = []
        for name in COMPOSITION_ORDER:
            content = files.get(name, "")
            if not content:
                continue
            title = _SECTION_TITLES.get(name, name)
            parts.append(f"# {title}\n{content}")
        sections["base"] = "\n\n".join(parts)
        return sections
