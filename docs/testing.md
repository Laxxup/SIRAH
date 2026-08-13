# Pruebas

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
- Replay supports two sources: versioned JSONL manifests with small image
  fixtures in `tests/replay/fixtures/`, and optional `.mp4` files with JSONL
  annotations. Keep real recordings in `tests/replay/data/`, outside normal Git
  or managed with Git LFS.
- HIL tests require explicit operator approval and are not CI prerequisites.
- Las pruebas conversacionales usan fakes para STT, Ollama, TTS, `ffmpeg` y
  reproducción; no requieren micrófono, bocina, Edge, Groq ni Ollama Cloud.
- Las pruebas live de conversación siguen el protocolo de
  [laboratorio](laboratory/voice-latency-baseline.md). Registra solo métricas,
  no contenido de usuarios o proveedores.
