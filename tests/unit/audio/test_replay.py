from __future__ import annotations

from pathlib import Path

import pytest

from sirah.audio.replay import load_replay

FIXTURE = Path(__file__).parents[2] / "fixtures/audio/synthetic_audio_replay.jsonl"


def test_replay_loads_synthetic_chunks_and_transcript_segments():
    replay = load_replay(FIXTURE)

    assert [chunk.observed_at for chunk in replay.chunks] == [1.0, 1.02]
    assert replay.chunks[0].pcm == b"\x00\x01\x02\x03"
    assert replay.transcripts[0].text == "hola sirah"


def test_replay_rejects_invalid_base64(tmp_path: Path):
    fixture = tmp_path / "invalid.jsonl"
    fixture.write_text(
        '{"kind":"chunk","pcm_b64":"?","sample_rate":16000,'
        '"channels":1,"observed_at":1.0}\n'
    )

    with pytest.raises(ValueError):
        load_replay(fixture)
