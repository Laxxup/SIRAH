"""Contract gate: Python and C++ parsers over the same golden corpus.

Verifies:
  1. The Python parser matches every corpus expectation (protocol.md
     sections 4-9, deterministic error order).
  2. The C++ host-side reference parser matches the same corpus.
  3. Both parsers produce identical verdict sequences (no divergence).
  4. The spec verb -> response mapping (protocol.md 6.2) is encoded as
     documented in the contract table.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sirah.protocol.parse_line import VERB_RESPONSE, parse_line
from tests.contract.corpus import GOLDEN_DIR, load_cases

REPO_ROOT = Path(__file__).resolve().parents[2]
HOST_DIR = REPO_ROOT / "firmware/sirah-eyes/tests/host"
CHECKER = HOST_DIR / "build" / "contract_checker"

CASES = load_cases()


def run_checker() -> list[tuple[int, str]]:
    subprocess.run(
        ["make", "-C", str(HOST_DIR), "contract_checker"],
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        [str(CHECKER), str(GOLDEN_DIR)], check=True, capture_output=True, text=True
    )
    got: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        if line.startswith("i="):
            idx_s, _, verdict = line.partition(" ")
            got.append((int(idx_s.removeprefix("i=")), verdict.removeprefix("got=")))
    return got


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[2]}#{c[1]}")
def test_python_matches_corpus(case: tuple[bytes, str, str]) -> None:
    raw, expected, _ = case
    assert parse_line(raw).verdict() == expected


def test_python_parser_never_diverges_from_c_oracle() -> None:
    python = [parse_line(raw).verdict() for raw, _, _ in CASES]
    cpp = [v for _, v in run_checker()]
    assert len(cpp) == len(python)
    assert cpp == python


def test_cpp_checker_reports_all_pass() -> None:
    proc = subprocess.run(
        [str(CHECKER), str(GOLDEN_DIR)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout
    summary = [l for l in proc.stdout.splitlines() if l.startswith("TOTAL")]
    assert summary and "FAILED 0" in summary[-1]


def test_verb_response_mapping_from_spec() -> None:
    # protocol.md 6.2: TARGET/CENTER/BLINK -> OK, HEARTBEAT -> silent,
    # STATUS -> STATE. The parser returns the command; the response class
    # follows the spec table (consumed by the runtime in later stages).
    assert VERB_RESPONSE == {
        "TARGET": "OK",
        "CENTER": "OK",
        "BLINK": "OK",
        "HEARTBEAT": "SILENT",
        "STATUS": "STATE",
    }


def test_corpus_coverage_is_declared() -> None:
    counts: dict[str, int] = {}
    for _, expected, source in CASES:
        counts[source] = counts.get(source, 0) + 1
    assert counts == {
        "commands_valid.txt": 19,
        "commands_invalid.txt": 18,
        "numbers_limits.txt": 21,
        "framing_encoding.txt": 10,
        "responses.txt": 23,
    }
    assert len(CASES) == 91