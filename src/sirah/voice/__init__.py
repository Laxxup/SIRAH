"""Voice layer — STT, TTS, audio coordination."""

from __future__ import annotations

__all__ = [
    "SpeechInputPort",
    "SpeechOutputPort",
    "WhisperSTT",
    "PiperTTS",
    "GTTSTTS",
    "MicCapture",
    "AudioTurnCoordinator",
    "FakeSpeechInput",
    "FakeSpeechOutput",
]

from sirah.voice.coordinator import AudioTurnCoordinator
from sirah.voice.mic_capture import MicCapture
from sirah.voice.port import SpeechInputPort, SpeechOutputPort
from sirah.voice.simulated import FakeSpeechInput, FakeSpeechOutput
from sirah.voice.stt_whisper import WhisperSTT
from sirah.voice.tts_gtts import GTTSTTS
from sirah.voice.tts_piper import PiperTTS
