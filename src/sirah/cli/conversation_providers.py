"""Provider selection for the conversation CLI.

`_proposer`, `_operation_stt`, `_operation_tts` and `_device_id` map CLI
provider names and the environment to the actual LLM/STT/TTS adapters.
`_ollama_configured` lives here too so both the hub and the live modes can
gate on configuration without an import cycle.
"""

from __future__ import annotations

import os

from sirah.audio.groq_stt import GroqWhisperSTT
from sirah.audio.stt import FasterWhisperSTT
from sirah.audio.tts import AsyncTTS
from sirah.conversation.ollama import OllamaIntentProposer
from sirah.conversation.session import OperationTTS


def _device_id(value: str | None) -> int | str | None:
    return int(value) if value is not None and value.isdecimal() else value


def _ollama_configured() -> bool:
    return bool(os.getenv("SIRAH_OLLAMA_HOST") and os.getenv("SIRAH_OLLAMA_MODEL"))


def _proposer(model: str | None = None) -> OllamaIntentProposer:
    env = dict(os.environ)
    if model:
        env["SIRAH_OLLAMA_MODEL"] = model
    return OllamaIntentProposer.from_environment(environ=env)


def _operation_tts(provider: str) -> tuple[OperationTTS, int]:
    if provider == "local":
        from sirah.audio.kokoro_tts import KokoroTextToSpeech

        return AsyncTTS(KokoroTextToSpeech.from_environment), KokoroTextToSpeech.sample_rate
    if provider == "edge":
        from sirah.audio.edge_tts import EdgeTextToSpeech
        from sirah.audio.kokoro_tts import KokoroTextToSpeech
        from sirah.audio.tts import FallbackTTS

        # Edge is a network provider; fall back to the local Kokoro voice at
        # the same sample rate (24 kHz) when the cloud is unreachable.
        return (
            FallbackTTS(
                EdgeTextToSpeech.from_environment,
                KokoroTextToSpeech.from_environment,
                on_fallback=lambda exc: print(f"edge TTS falló; usando voz local: {type(exc).__name__}"),
            ),
            EdgeTextToSpeech.sample_rate,
        )
    from sirah.audio.azure_tts import AzureOperationTextToSpeech, AzureTextToSpeech

    return AzureOperationTextToSpeech(AzureTextToSpeech.from_environment()), 16_000


def _operation_stt(provider: str, model: str, language: str):
    if provider == "groq":
        return GroqWhisperSTT.from_environment()
    return FasterWhisperSTT(model, language=language)