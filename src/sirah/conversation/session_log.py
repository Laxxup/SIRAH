"""Explicitly authorized, privacy-preserving JSONL session diagnostics."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from time import monotonic
from typing import Any

SCHEMA_VERSION = 1


class SessionLog:
    def __init__(self, *, include_text: bool = False, state_home: Path | None = None) -> None:
        root = state_home or Path(os.getenv("XDG_STATE_HOME", "~/.local/state")).expanduser()
        self.directory = root / "sirah" / "sessions"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.session_id = secrets.token_hex(8)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        self.path = self.directory / f"{timestamp}_{self.session_id}.jsonl"
        self._file = self.path.open("x", encoding="utf-8")
        os.chmod(self.path, 0o600)
        self.include_text = include_text
        self.write("session_started")

    def write(self, event: str, *, turn_id: int | None = None, **fields: Any) -> None:
        safe = {key: value for key, value in fields.items() if key not in {"audio", "pcm", "headers", "token", "key", "secret"}}
        if not self.include_text:
            safe = {key: value for key, value in safe.items() if key not in {"transcript", "raw_model_speech", "validated_speech", "local_response"}}
        record = {"schema_version": SCHEMA_VERSION, "timestamp_utc": datetime.now(UTC).isoformat(), "monotonic_ms": round(monotonic() * 1000), "session_id": self.session_id, "turn_id": turn_id, "event": event, **safe}
        self._file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self.write("session_stopped")
            self._file.close()


def session_directory(state_home: Path | None = None) -> Path:
    root = state_home or Path(os.getenv("XDG_STATE_HOME", "~/.local/state")).expanduser()
    return root / "sirah" / "sessions"


def session_files(state_home: Path | None = None) -> list[Path]:
    directory = session_directory(state_home)
    return sorted(directory.glob("*.jsonl"), reverse=True) if directory.is_dir() else []


def resolve_session(identifier: str, state_home: Path | None = None) -> Path:
    files = session_files(state_home)
    if identifier == "latest":
        if not files:
            raise FileNotFoundError("no SIRAH session logs exist")
        return files[0]
    matches = [path for path in files if path.stem.endswith(f"_{identifier}")]
    if len(matches) != 1:
        raise FileNotFoundError("unknown SIRAH session id")
    return matches[0]


def diagnose(path: Path) -> list[dict[str, str]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    findings: list[dict[str, str]] = []
    events = [record.get("event") for record in records]
    findings.append({"check": "clean_close", "result": "PASS" if "session_stopped" in events else "WARN"})
    findings.append({"check": "low_confidence", "result": "WARN" if "transcript_rejected" in events else "NOT_EVALUATED"})
    findings.append({"check": "duplicate_states", "result": "WARN" if any(a == b for a, b in pairwise(events)) else "PASS"})
    return findings


def delete_session(identifier: str, state_home: Path | None = None) -> Path:
    path = resolve_session(identifier, state_home)
    path.unlink()
    return path


def purge_sessions(state_home: Path | None = None, *, keep: int = 20) -> list[Path]:
    removed: list[Path] = []
    for path in session_files(state_home)[keep:]:
        path.unlink()
        removed.append(path)
    return removed
