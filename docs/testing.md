# Pruebas

Ejecuta el gate de software completo:

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run mypy
make -C firmware/sirah-eyes/tests/host core_tests
```

- Los unit tests cubren runtime puro, protocolo, config y helpers de percepción.
- Los contract tests comparan los parsers de Python y C++ contra el corpus golden.
- Los integration tests usan fakes de punta a punta y no requieren hardware.
- Replay soporta dos fuentes: manifests JSONL versionados con fixtures de imagen
  pequeñas en `tests/replay/fixtures/`, y archivos `.mp4` opcionales con
  anotaciones JSONL. Guarda grabaciones reales en `tests/replay/data/`, fuera
  del Git normal o con Git LFS.
- Los tests HIL requieren aprobación explícita del operador y no son
  prerequisitos de CI.
- Las pruebas conversacionales usan fakes para STT, Ollama, TTS, `ffmpeg` y
  reproducción; no requieren micrófono, bocina, Edge, Groq ni Ollama Cloud.
- Las pruebas live de conversación siguen el protocolo de
  [laboratorio](laboratory/voice-latency-baseline.md). Registra solo métricas,
  no contenido de usuarios o proveedores.