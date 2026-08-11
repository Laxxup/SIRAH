from __future__ import annotations

import sirah.cli.conversation as conversation_cli
from sirah.audio.tts import AsyncTTS
from sirah.cli.conversation import _device_id, _operation_tts, build_parser


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


def test_cli_exposes_local_tts_provider_without_azure_arguments():
    parser = build_parser()

    assert parser.parse_args(("tts-check", "--live", "--provider", "local")).provider == "local"
    assert parser.parse_args(("listen", "--live", "--tts-provider", "local")).tts_provider == "local"


def test_local_provider_selection_does_not_read_azure_configuration():
    tts, sample_rate = _operation_tts("local")

    assert isinstance(tts, AsyncTTS)
    assert sample_rate == 24_000


def test_listen_exposes_opt_in_diagnostics_flags():
    args = build_parser().parse_args(("listen", "--live", "--lab", "--show-text", "--record-session", "--include-text"))

    assert args.lab and args.show_text and args.record_session and args.include_text
