"""Wire-contract codec for the PC<->ESP32 link (protocol.md v1.0).

Transport-independent: pure payload encoding with no I/O, no clock and no
configuration. The grammar AUTHORITY is `sirah.protocol.parse_line` (both
sides are gated by the same golden corpus); this module adds only the
symmetric encode side and typed commands (ADR-0003, Stage 5).

Rules enforced here mirror the firmware parser error conditions:
- unknown verb        -> ContractError (firmware ERR 1)
- wrong arity /       -> ContractError (firmware ERR 2)
- payload > 63 bytes
- number outside      -> ContractError (firmware ERR 3)
  [-1, 1]

Payloads never include the trailing "\\n": framing is an adapter concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from sirah.protocol.parse_line import (
    COMMAND_ARITY,
    MAX_COORD,
    MAX_PAYLOAD_BYTES,
    MIN_COORD,
    parse_line,
)


class ContractError(ValueError):
    """Invalid message: unknown verb, wrong arity, bad number or too long."""


def format_coord(value: float) -> str:
    """Canonical coordinate per spec 5: <=3 decimals, no trailing zeros."""
    rounded = round(value, 3)
    text = f"{rounded:.3f}".rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


@dataclass(frozen=True)
class Command:
    """One command message: verb + positional args (after formatting)."""

    name: str
    args: tuple[str | float, ...] = ()

    def encode(self) -> bytes:
        return encode_command(self.name, self.args)


def encode_command(name: str, args: tuple[str | float, ...] = ()) -> bytes:
    """Encode a command to a payload (no trailing "\\n")."""
    verb = name.encode("ascii")
    if verb not in COMMAND_ARITY:
        raise ContractError(f"unknown command: {name}")
    expected = COMMAND_ARITY[verb]
    if len(args) != expected:
        raise ContractError(
            f"{name} expects {expected} args, got {len(args)}"
        )

    tokens = [verb]
    for arg in args:
        if verb == b"TARGET":
            try:
                value = float(arg)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"TARGET arg not a number: {arg!r}") from exc
            if not (MIN_COORD <= value <= MAX_COORD):
                raise ContractError(
                    f"TARGET arg {value!r} outside [{MIN_COORD}, {MAX_COORD}]"
                )
            tokens.append(format_coord(value).encode("ascii"))
        else:
            tokens.append(str(arg).encode("ascii"))
    payload = b" ".join(tokens)
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ContractError(
            f"payload {len(payload)} bytes > {MAX_PAYLOAD_BYTES} (spec 4)"
        )
    return payload


def decode_payload(payload: bytes):
    """Decode one payload exactly like the authoritative parser."""
    return parse_line(payload)