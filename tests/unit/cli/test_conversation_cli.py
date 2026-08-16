from __future__ import annotations

import sirah.cli.conversation as conversation_cli
from sirah.audio.groq_stt import GroqWhisperSTT
from sirah.audio.stt import FasterWhisperSTT
from sirah.audio.tts import AsyncTTS
from sirah.cli.conversation import (
    _device_id,
    _operation_stt,
    _operation_tts,
    build_parser,
)


def test_conversation_cli_exposes_operational_commands():
    parser = build_parser()

    commands = (("devices",), ("replay", "fixture.jsonl"), ("ollama-check",), ("config",), ("listen",), ("push-to-talk",))
    for arguments in commands:
        assert parser.parse_args(arguments).command == arguments[0]


def test_listen_accepts_text_only_without_tts_configuration():
    arguments = build_parser().parse_args(("listen", "--live", "--text-only"))

    assert arguments.text_only is True


def test_device_id_converts_numeric_cli_values_but_keeps_device_names():
    assert _device_id("22") == 22
    assert _device_id("Default Source") == "Default Source"


def test_listen_handles_ctrl_c_without_a_traceback(monkeypatch, capsys):
    def interrupt(_coroutine):
        _coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(conversation_cli.asyncio, "run", interrupt)

    assert conversation_cli.main(("listen", "--live", "--text-only")) == 0
    assert capsys.readouterr().out == ""


def test_push_to_talk_handles_ctrl_c_without_a_traceback(monkeypatch, capsys):
    def interrupt(_coroutine):
        _coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(conversation_cli.asyncio, "run", interrupt)

    assert conversation_cli.main(("push-to-talk", "--live", "--text-only")) == 0
    assert capsys.readouterr().out == "Cloud transcripts may leave this device. Press Ctrl-C to stop after speaking.\n"


def test_cli_exposes_tts_providers_without_azure_arguments():
    parser = build_parser()

    assert parser.parse_args(("tts-check", "--live", "--provider", "local")).provider == "local"
    assert parser.parse_args(("listen", "--live", "--tts-provider", "local")).tts_provider == "local"
    assert parser.parse_args(("tts-check", "--live", "--provider", "edge")).provider == "edge"
    assert parser.parse_args(("listen", "--live", "--tts-provider", "edge")).tts_provider == "edge"


def test_tts_check_accepts_an_operator_phrase():
    args = build_parser().parse_args(("tts-check", "--live", "--provider", "edge", "--text", "SIRAH iniciada."))

    assert args.text == "SIRAH iniciada."


def test_tts_check_accepts_latency_diagnostics():
    args = build_parser().parse_args(("tts-check", "--live", "--provider", "edge", "--lab"))

    assert args.lab is True


def test_cli_exposes_local_and_groq_stt_providers():
    parser = build_parser()

    assert parser.parse_args(("listen", "--live", "--stt-provider", "local")).stt_provider == "local"
    assert parser.parse_args(("push-to-talk", "--live", "--stt-provider", "groq")).stt_provider == "groq"


def test_stt_provider_selection_returns_the_requested_adapter(monkeypatch):
    monkeypatch.setenv("SIRAH_GROQ_API_KEY", "secret")

    assert isinstance(_operation_stt("local", "base", "es"), FasterWhisperSTT)
    assert isinstance(_operation_stt("groq", "base", "es"), GroqWhisperSTT)


def test_local_provider_selection_does_not_read_azure_configuration():
    tts, sample_rate = _operation_tts("local")

    assert isinstance(tts, AsyncTTS)
    assert sample_rate == 24_000


def test_edge_provider_selection_uses_24khz_pcm_with_local_fallback():
    from sirah.audio.tts import FallbackTTS

    tts, sample_rate = _operation_tts("edge")

    assert isinstance(tts, FallbackTTS)
    assert sample_rate == 24_000


def test_listen_exposes_opt_in_diagnostics_flags():
    args = build_parser().parse_args(("listen", "--live", "--lab", "--show-text", "--record-session", "--include-text"))

    assert args.lab and args.show_text and args.record_session and args.include_text


def test_lab_metrics_format_reports_capture_queue_health():
    assert conversation_cli._capture_metrics(0, 1) == "captura: sin descartes; cola max 1/8"
    assert conversation_cli._capture_metrics(2, 8) == "captura: 2 frames descartados; cola max 8/8"


def test_lab_diagnostic_shows_category_without_private_provider_detail(capsys):
    conversation_cli._show_lab_diagnostic("propuesta descartada: InvalidModelResponse")

    assert capsys.readouterr().out == "diagnóstico: propuesta descartada: InvalidModelResponse\n"


def test_ollama_stream_probe_accepts_live_prompt_and_context_limit():
    args = build_parser().parse_args(
        ("ollama-stream-probe", "--live", "--prompt", "prueba", "--context-limit", "4", "--think", "false")
    )

    assert args.live is True
    assert args.prompt == "prueba"
    assert args.context_limit == 4
    assert args.think == "false"
