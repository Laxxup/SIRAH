from __future__ import annotations

import pytest

from sirah.audio.azure_tts import AzureTextToSpeech
from sirah.conversation.errors import ConfigurationError


async def test_azure_tts_requires_explicit_environment_configuration():
    with pytest.raises(ConfigurationError):
        AzureTextToSpeech.from_environment(environ={})


async def test_azure_tts_uses_injected_transport_without_network():
    calls: list[tuple[str, dict[str, str], bytes]] = []

    async def post(url: str, headers: dict[str, str], body: bytes) -> bytes:
        calls.append((url, headers, body))
        return b"pcm"

    tts = AzureTextToSpeech.from_environment(
        environ={"SIRAH_AZURE_SPEECH_KEY": "test", "SIRAH_AZURE_SPEECH_REGION": "eastus"},
        post=post,
    )

    assert await tts.synthesize("hola") == b"pcm"
    assert "test" not in calls[0][2].decode()
    assert "es-MX-DaliaNeural" in calls[0][2].decode()
