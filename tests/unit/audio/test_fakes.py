from __future__ import annotations

import pytest

from sirah.audio.contracts import AudioChunk, Transcript
from sirah.audio.fakes import (
    FakeAudioSource,
    FakeOperationTTS,
    FakePCMPlayer,
    FakeSTT,
)


async def test_fake_audio_source_yields_chunks_in_timestamp_order_then_eof():
    chunks = (
        AudioChunk(b"a", 16000, 1, 1.0),
        AudioChunk(b"b", 16000, 1, 1.02),
    )
    source = FakeAudioSource(chunks)

    await source.start()
    assert await source.next_chunk() == chunks[0]
    assert await source.next_chunk() == chunks[1]
    assert await source.next_chunk() is None
    await source.stop()


async def test_fake_audio_source_can_fail_at_a_chunk():
    source = FakeAudioSource(
        (AudioChunk(b"a", 16000, 1, 1.0),),
        fail_at=0,
        failure=RuntimeError("capture failed"),
    )

    await source.start()
    with pytest.raises(RuntimeError, match="capture failed"):
        await source.next_chunk()


async def test_fake_stt_records_input_and_returns_configured_transcript():
    transcript = Transcript("hola", 1.0, 1.5, 0.9)
    chunk = AudioChunk(b"a", 16000, 1, 1.0)
    stt = FakeSTT(transcript)

    assert await stt.transcribe((chunk,)) == transcript
    assert stt.requests == [(chunk,)]


async def test_operation_audio_fakes_record_synthesis_playback_and_cancellation():
    tts = FakeOperationTTS(pcm=b"synthetic-pcm")
    player = FakePCMPlayer()

    pcm = await tts.synthesize("conversation-1", "hola")
    await player.play("conversation-1", pcm)
    await tts.cancel("conversation-2")
    await player.cancel("conversation-2")

    assert tts.requests == [("conversation-1", "hola")]
    assert player.played == [("conversation-1", b"synthetic-pcm")]
    assert tts.cancelled == ["conversation-2"]
    assert player.cancelled == ["conversation-2"]
