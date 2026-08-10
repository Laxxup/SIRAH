# Testing

Run the complete software gate:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/python -m mypy src
make -C firmware/sirah-eyes/tests/host core_tests
```

- Unit tests cover pure runtime, protocol, config and perception helpers.
- Contract tests compare the Python and C++ parsers against the golden corpus.
- Integration tests use fakes end to end and require no hardware.
- Replay tests use finite recorded payloads; datasets remain local.
- HIL tests require explicit operator approval and are not CI prerequisites.
