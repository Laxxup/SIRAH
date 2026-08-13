from __future__ import annotations

import json
from pathlib import Path

from sirah.audio.fakes import FakeOperationTTS, FakePCMPlayer
from sirah.audio.replay import load_replay
from sirah.conversation.ollama import OllamaIntentProposer
from sirah.conversation.session import ConversationSession
from sirah.evaluation.conversation import replay_transcripts

FIXTURES = Path(__file__).parents[1] / "fixtures/conversation"
ENVIRONMENT = {
    "SIRAH_OLLAMA_HOST": "https://offline.invalid",
    "SIRAH_OLLAMA_MODEL": "offline-model",
    "SIRAH_OLLAMA_API_KEY": "offline-key",
}


async def test_transcript_replay_plays_approved_ollama_response_and_reports_metrics():
    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        return json.dumps(
            {
                "message": {
                    "content": json.dumps(
                        {
                            "intent": "answer",
                            "speech": "Hola, en que puedo ayudarte?",
                            "emotion": "friendly",
                            "action": "none",
                        }
                    )
                }
            }
        ).encode()

    tts = FakeOperationTTS(pcm=b"synthetic-pcm")
    player = FakePCMPlayer()
    session = ConversationSession(
        OllamaIntentProposer.from_environment(
            environ=ENVIRONMENT, timeout_s=10.0, budget=1, post=post
        ),
        tts,
        player,
    )

    metrics = await replay_transcripts(load_replay(FIXTURES / "approved.jsonl").transcripts, session)

    assert metrics.turns == 1
    assert metrics.accepted == 1
    assert metrics.fallback == 0
    assert metrics.played == 1
    assert metrics.cancelled == 0
    assert tts.requests == [("conversation-1", "Hola, en que puedo ayudarte?")]
    assert player.played == [("conversation-1", b"synthetic-pcm")]


async def test_malformed_ollama_json_plays_spoken_recovery():
    async def post(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> bytes:
        return b'{"message":{"content":"not json"}}'

    tts = FakeOperationTTS()
    player = FakePCMPlayer()
    session = ConversationSession(
        OllamaIntentProposer.from_environment(
            environ=ENVIRONMENT, timeout_s=10.0, budget=1, post=post
        ),
        tts,
        player,
    )

    metrics = await replay_transcripts(load_replay(FIXTURES / "malformed.jsonl").transcripts, session)

    assert metrics.turns == 1
    assert metrics.accepted == 1
    assert metrics.fallback == 0
    assert metrics.played == 1
    assert metrics.cancelled == 0
    assert tts.requests == [("conversation-1", "No entendí bien, ¿puedes repetirlo?")]
    assert player.played == [("conversation-1", b"synthetic-pcm")]


def test_conversation_fixtures_store_transcripts_without_raw_pcm():
    for fixture in FIXTURES.glob("*.jsonl"):
        for line in fixture.read_text().splitlines():
            entry = json.loads(line)
            assert set(entry) == {
                "kind",
                "text",
                "started_at",
                "ended_at",
                "confidence",
            }
            assert entry["kind"] == "transcript"
