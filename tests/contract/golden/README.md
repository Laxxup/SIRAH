# Golden corpus — PC↔ESP32 contract (protocol.md v1.0)

One test case per line:

```
<input>|<expected>
```

- `<input>`: raw line payload, **no trailing `\n`**. Non-printable or
  non-ASCII bytes are written as `\xHH` escapes (decoded by both loaders
  before parsing: `tests/contract/corpus.py` and the C++ checker).
- `<expected>`: verdict token — `CMD:<VERB>`, `RESP:<TOKEN>`,
  `ERR:<code>`, or `IGNORE` (spec §9.5, empty line).
- The first `|` separates input from expected; inputs never contain a
  literal `|`.

Both the Python parser (`src/sirah/protocol/parse_line.py`) and the C++
host-side reference parser (`firmware/sirah-eyes/tests/host/protocol_parser.*`)
consume this same corpus; the contract gate requires identical verdict
sequences (tests/contract/test_parsers_contract.py).

## Files and coverage

| File | Cases | Coverage |
|---|---|---|
| `commands_valid.txt` | 19 | Every verb; canonical and lax-but-valid number formats (`0`, `-0`, `-0.000`, `1.000`); inclusive boundaries; repetition/idempotency cases |
| `commands_invalid.txt` | 18 | Unknown verb (incl. lowercase), wrong arity (missing/extra), bad tokens, double space, leading space, trailing space, tab (escaped) |
| `numbers_limits.txt` | 21 | Out-of-range (ERR 3) incl. huge integers; malformed syntax (ERR 2: `+1`, `00.5`, `.5`, `1.`, 4 decimals, `1e0`, `0,5`, `--1`, `-`); inclusive boundaries as valid |
| `framing_encoding.txt` | 10 | 63-byte line (length OK → ERR 1 by verb dominance, per §9.2 order), 64-byte line (ERR 2, length wins), empty line (IGNORE), `\r`, embedded `\n`, DEL 0x7F, non-ASCII 0xC3/0xA9, leading tab, vertical tab |
| `responses.txt` | 23 | All four response tokens valid; malformed responses (`READY 0`, `STATE 0 0`, blink not 0/1, `ERR 4`/`ERR 0`/`ERR 9`, extra args, out-of-range STATE coords, lowercase) |

Total: **91 cases**.

## Interpretation notes (recorded for traceability)

- Error codes follow the deterministic order of protocol.md §9.2: length
  → printable → verb → arity → syntax → range; the FIRST failing check
  wins (e.g., 64-byte line → ERR 2 regardless of content; 63-byte unknown
  verb → ERR 1; leading space → ERR 1 — empty first token is an unknown
  verb; double/trailing space → ERR 2 — arity mismatch).
- Malformed RESPONSE lines are classified with the same closed-grammar
  rules as commands (unified interpretation; ratified in Stage 2 — see
  the ambiguity report). Responses never use ERR 4 (reserved).
- `TARGET 1 0`-style entries with both arguments valid are command
  outcomes (range applies per argument: any out-of-range arg → ERR 3).
- The valid 63-byte line demonstrates the framing limit itself: 63
  payload bytes + `\n` = 64 bytes total = legal per spec §4; the next
  byte pushes it to ERR 2.