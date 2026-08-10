"""Contract codec tests (Stage 5).

The authoritative parser lives in sirah.protocol.parse_line and is gated
by the golden corpus (Stage 3). These tests pin the SYMMETRIC encode side:
encodings must parse back to the canonical verdict, match the corpus's
number conventions (<=3 decimals), and reproduce the firmware's error
conditions (unknown verb, arity, range, length).
"""

from __future__ import annotations

import pytest

from sirah.hardware.contract import (
    Command,
    ContractError,
    decode_payload,
    encode_command,
    format_coord,
)


def test_format_coord_canonical() -> None:
    assert format_coord(0.0) == "0"
    assert format_coord(-0.0) == "0"
    assert format_coord(1.0) == "1"
    assert format_coord(-1.0) == "-1"
    assert format_coord(0.5) == "0.5"
    assert format_coord(-0.25) == "-0.25"
    assert format_coord(0.3333) == "0.333"
    assert format_coord(0.6666) == "0.667"
    assert format_coord(0.5e-3) == "0.001"  # 3 decimals max


def test_encode_then_decode_roundtrip() -> None:
    payload = encode_command("TARGET", (0.333, 0.667))
    assert payload == b"TARGET 0.333 0.667"
    result = decode_payload(payload)
    assert result.name == "TARGET"
    assert result.args == (b"0.333", b"0.667")


def test_encode_zero_arg_commands() -> None:
    assert encode_command("CENTER") == b"CENTER"
    assert encode_command("BLINK") == b"BLINK"
    assert encode_command("HEARTBEAT") == b"HEARTBEAT"
    assert encode_command("STATUS") == b"STATUS"


def test_command_dataclass_encode() -> None:
    cmd = Command("TARGET", (1.0, -0.5))
    assert cmd.encode() == b"TARGET 1 -0.5"


def test_unknown_verb_rejected() -> None:
    with pytest.raises(ContractError):
        encode_command("WIGGLE")


def test_wrong_arity_rejected() -> None:
    with pytest.raises(ContractError):
        encode_command("CENTER", (0.5,))
    with pytest.raises(ContractError):
        encode_command("TARGET", (0.5,))


def test_out_of_range_number_rejected() -> None:
    with pytest.raises(ContractError):
        encode_command("TARGET", (1.5, 0.0))
    with pytest.raises(ContractError):
        encode_command("TARGET", (0.0, -1.01))


def test_non_numeric_target_rejected() -> None:
    with pytest.raises(ContractError):
        encode_command("TARGET", ("left", 0.0))


def test_all_valid_encodes_fit_payload_limit() -> None:
    from sirah.protocol.parse_line import MAX_PAYLOAD_BYTES

    for i in range(101):
        payload = encode_command("TARGET", (i / 100.0, -i / 100.0))
        assert len(payload) <= MAX_PAYLOAD_BYTES
    assert len(encode_command("STATUS")) <= MAX_PAYLOAD_BYTES


def test_decode_delegates_to_authoritative_parser() -> None:
    # Matches the golden corpus verdicts (errors map 1:1 to firmware).
    assert decode_payload(b"GARBAGE").code == 1
    assert decode_payload(b"").kind == "ignore"
    assert decode_payload(b"STATE 0.0 0.0 1").name == "STATE"
    assert decode_payload(b"TARGET 2 0").code == 3  # out of range