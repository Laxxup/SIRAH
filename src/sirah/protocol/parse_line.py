"""Canonical PC<->ESP32 line parser (protocol.md v1.0).

Pure parser: no transports, no configuration, no behavior logic.
Operates on bytes: the payload of a line WITHOUT the trailing "\\n"
(framing handled by the transport adapter later).

Implements sections 4-9 of docs/components/protocol.md:
length limit, printable ASCII, verb/token recognition, exact arity,
number syntax and range, deterministic error order (first failing check).

Authoritative for the Python side; the C++ host-side reference parser
(firmware/sirah-eyes/tests/host/protocol_parser.*) mirrors it; both are
checked against the same golden corpus (tests/contract/golden).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# spec 4: max line length 64 bytes INCLUDING the terminating "\\n"
MAX_PAYLOAD_BYTES = 63

# spec 6.2 (commands) and 7.1 (responses): token -> fixed arity
COMMAND_ARITY = {
    b"TARGET": 2,
    b"CENTER": 0,
    b"BLINK": 0,
    b"HEARTBEAT": 0,
    b"STATUS": 0,
}
RESPONSE_ARITY = {
    b"READY": 1,
    b"OK": 0,
    b"STATE": 3,
    b"ERR": 1,
}

# spec 5: decimal syntax, <= 3 decimals
NUM_RE = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?$")

MIN_COORD = -1.0
MAX_COORD = 1.0
READY_VERSION = b"1"
BLINK_TOKENS = (b"0", b"1")
ERR_CODES = (b"1", b"2", b"3", b"5")


@dataclass(frozen=True)
class ParseResult:
    """kind: "cmd" | "resp" | "err" | "ignore"."""

    kind: str
    name: str | None = None
    args: tuple[bytes, ...] = ()
    code: int | None = None

    def verdict(self) -> str:
        if self.kind == "cmd":
            return f"CMD:{self.name}"
        if self.kind == "resp":
            return f"RESP:{self.name}"
        if self.kind == "err":
            return f"ERR:{self.code}"
        return "IGNORE"


def _is_printable(line: bytes) -> bool:
    return all(0x20 <= c <= 0x7E for c in line)


def _num_in_range(token: bytes) -> bool:
    return MIN_COORD <= float(token) <= MAX_COORD


def parse_line(line: bytes) -> ParseResult:
    """Parse one payload (without "\\n"). Returns a ParseResult."""
    if len(line) > MAX_PAYLOAD_BYTES:
        return ParseResult("err", code=2)
    if not _is_printable(line):
        return ParseResult("err", code=2)
    tokens = line.split(b" ")
    if line == b"":
        return ParseResult("ignore")
    name = tokens[0]
    if name not in COMMAND_ARITY and name not in RESPONSE_ARITY:
        return ParseResult("err", name=None, code=1)

    is_cmd = name in COMMAND_ARITY
    arity = COMMAND_ARITY[name] if is_cmd else RESPONSE_ARITY[name]
    args = tuple(tokens[1:]) if len(tokens) > 1 else ()
    if len(args) != arity:
        return ParseResult("err", code=2)

    if name == b"TARGET":
        for a in args:
            if not NUM_RE.match(a):
                return ParseResult("err", code=2)
            if not _num_in_range(a):
                return ParseResult("err", code=3)
        return ParseResult("cmd", name="TARGET", args=args)

    if is_cmd:
        return ParseResult("cmd", name=name.decode("ascii"))

    if name == b"READY":
        if args[0] != READY_VERSION:
            return ParseResult("err", code=2)
        return ParseResult("resp", name="READY", args=args)

    if name == b"STATE":
        x, y, blink = args
        for a in (x, y):
            if not NUM_RE.match(a):
                return ParseResult("err", code=2)
            if not _num_in_range(a):
                return ParseResult("err", code=3)
        if blink not in BLINK_TOKENS:
            return ParseResult("err", code=2)
        return ParseResult("resp", name="STATE", args=args)

    if name == b"ERR":
        if args[0] not in ERR_CODES:
            return ParseResult("err", code=2)
        return ParseResult("resp", name="ERR", args=args)

    if name == b"OK":
        return ParseResult("resp", name="OK")

    raise AssertionError(f"unreachable: {name!r}")

# Spec 6.2: verb -> response class, verified by the contract tests.
VERB_RESPONSE = {
    "TARGET": "OK",
    "CENTER": "OK",
    "BLINK": "OK",
    "HEARTBEAT": "SILENT",
    "STATUS": "STATE",
}