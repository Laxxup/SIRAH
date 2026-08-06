"""Test voice layer — simulated speech input/output."""

from __future__ import annotations

import pytest

from sirah.errors import SpeechError, SpeechInputError
from sirah.types import SpeechRecognitionEvent
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput


@pytest.mark.asyncio
async def test_fake_speech_input_scripted() -> None:
    events = [
        SpeechRecognitionEvent(text="hola", is_final=True, confidence=0.9),
        SpeechRecognitionEvent(text="adiós", is_final=True, confidence=0.85),
    ]
    inp = FakeSpeechInput(scripted=events)
    await inp.start()
    r1 = await inp.listen()
    r2 = await inp.listen()
    assert r1.text == "hola"
    assert r2.text == "adiós"
    await inp.stop()


@pytest.mark.asyncio
async def test_fake_speech_input_empty_after_script() -> None:
    inp = FakeSpeechInput(scripted=[SpeechRecognitionEvent(text="único", is_final=True)])
    await inp.start()
    r1 = await inp.listen()
    assert r1.text == "único"
    r2 = await inp.listen()
    assert r2.text == ""


@pytest.mark.asyncio
async def test_fake_speech_input_failure() -> None:
    inp = FakeSpeechInput(fail_after=0)
    await inp.start()
    with pytest.raises(SpeechInputError, match="simulated failure"):
        await inp.listen()
    await inp.stop()


@pytest.mark.asyncio
async def test_fake_speech_input_health() -> None:
    inp = FakeSpeechInput()
    assert await inp.health() is False
    await inp.start()
    assert await inp.health() is True
    await inp.stop()
    assert await inp.health() is False


@pytest.mark.asyncio
async def test_fake_speech_input_reset() -> None:
    events = [SpeechRecognitionEvent(text="a", is_final=True)]
    inp = FakeSpeechInput(scripted=events)
    await inp.start()
    await inp.listen()
    assert inp._index == 1
    inp.reset()
    assert inp._index == 0


@pytest.mark.asyncio
async def test_fake_speech_output_speaks() -> None:
    out = FakeSpeechOutput()
    result = await out.speak("hola mundo")
    assert result.success
    assert len(out.spoken) == 1
    assert out.spoken[0] == "hola mundo"


@pytest.mark.asyncio
async def test_fake_speech_output_multiple() -> None:
    out = FakeSpeechOutput()
    await out.speak("uno")
    await out.speak("dos")
    assert out.spoken == ["uno", "dos"]


@pytest.mark.asyncio
async def test_fake_speech_output_failure() -> None:
    out = FakeSpeechOutput(fail_after=2)
    await out.speak("uno")
    await out.speak("dos")
    with pytest.raises(SpeechError, match="simulated failure"):
        await out.speak("tres")


@pytest.mark.asyncio
async def test_fake_speech_output_health() -> None:
    out = FakeSpeechOutput()
    assert await out.health() is True


@pytest.mark.asyncio
async def test_fake_speech_output_reset() -> None:
    out = FakeSpeechOutput()
    await out.speak("hola")
    assert len(out.spoken) == 1
    out.reset()
    assert len(out.spoken) == 0
