"""Golden corpus loader (tests/contract/golden).

Format of each golden file: one case per line,

    <input>|<expected>

- <input> is the raw payload of a protocol line (no trailing newline).
  Non-printable / non-ASCII bytes must be written as \\xHH escapes.
- <expected> is the parse verdict token: CMD:<VERB>, RESP:<TOKEN>,
  ERR:<code>, or IGNORE.

The first '|' separates input from expected; inputs never contain a
literal '|' (no corpus case uses it).
"""

from __future__ import annotations

from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"


def unescape(token: bytes) -> bytes:
    """Decode \\xHH escapes into raw bytes (only for control/non-ASCII)."""
    out = bytearray()
    i = 0
    while i < len(token):
        if token[i : i + 2] == b"\\x":
            out.append(int(token[i + 2 : i + 4].decode("ascii"), 16))
            i += 4
        else:
            out.append(token[i])
            i += 1
    return bytes(out)


def load_cases() -> list[tuple[bytes, str, str]]:
    """Return [(input_bytes, expected_token, source_file)] in file order."""
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.txt")):
        for line in path.read_bytes().split(b"\n"):
            if not line:
                continue
            raw_input, _, expected = line.partition(b"|")
            cases.append((unescape(raw_input), expected.decode("ascii"), path.name))
    return cases