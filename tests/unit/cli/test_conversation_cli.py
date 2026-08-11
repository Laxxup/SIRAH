from __future__ import annotations

from sirah.cli.conversation import build_parser


def test_conversation_cli_exposes_operational_commands():
    parser = build_parser()

    commands = (("devices",), ("replay", "fixture.jsonl"), ("ollama-check",), ("config",), ("listen",), ("push-to-talk",))
    for arguments in commands:
        assert parser.parse_args(arguments).command == arguments[0]


def test_listen_accepts_text_only_without_tts_configuration():
    arguments = build_parser().parse_args(("listen", "--live", "--text-only"))

    assert arguments.text_only is True
