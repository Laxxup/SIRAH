"""Loader for small, synthetic audio replay fixtures."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from sirah.audio.contracts import AudioChunk, Transcript


@dataclass(frozen=True)
class AudioReplay:
    chunks: tuple[AudioChunk, ...]
    transcripts: tuple[Transcript, ...]


def load_replay(path: Path) -> AudioReplay:
    chunks: list[AudioChunk] = []
    transcripts: list[Transcript] = []
    for line in path.read_text().splitlines():
        if not line:
            continue
        entry = json.loads(line)
        if entry["kind"] == "chunk":
            chunks.append(
                AudioChunk(
                    base64.b64decode(entry["pcm_b64"], validate=True),
                    entry["sample_rate"],
                    entry["channels"],
                    entry["observed_at"],
                )
            )
        elif entry["kind"] == "transcript":
            transcripts.append(
                Transcript(
                    entry["text"],
                    entry["started_at"],
                    entry["ended_at"],
                    entry["confidence"],
                )
            )
        else:
            raise ValueError(f"unknown audio replay entry: {entry['kind']!r}")
    return AudioReplay(tuple(chunks), tuple(transcripts))
