# Guía de release

Esta guía define el cierre de una release de SIRAH. Python 3.12 es la versión
mínima soportada.

## Prechecks obligatorios

Desde un entorno limpio, instala todas las dependencias de CI y ejecuta los
gates antes de crear una release:

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run mypy
make -C firmware/sirah-eyes/tests/host core_tests
make -C firmware/sirah-eyes/tests/host contract_checker
uv run pytest tests/contract -q
```

No descargues YuNet durante estos prechecks. El modelo se obtiene solo de forma
explícita para uso local; CI no requiere webcam, ESP32 ni otro hardware físico.

## Versión y tag

1. Confirma que la versión de `pyproject.toml` y `CHANGELOG.md` describen la
   misma release. El README muestra el estado del proyecto, no un número fijo.
2. Actualiza `CHANGELOG.md` con cambios verificables y sus límites conocidos.
3. Después de que los prechecks pasen, crea y publica un tag anotado con el
    formato `vX.Y.Z`, por ejemplo `v0.3.1`.
4. La publicación debe apuntar al commit exacto validado por los prechecks.

## Notas de release honestas

Describe solo capacidades implementadas y la evidencia disponible. Separa con
claridad lo validado en software, las verificaciones físicas realizadas y las
áreas en desarrollo. Indica resultados de CI únicamente cuando GitHub Actions
haya terminado correctamente para el commit etiquetado.

## Laboratorio conversacional

Si la release cambia STT, LLM, TTS, VAD o salida de audio, ejecuta además:

```bash
uv run sirah-conversation tts-check --live --provider edge --lab
uv run sirah-conversation ollama-stream-probe --live --think default
uv run sirah-conversation ollama-stream-probe --live --think low
```

Registra evidencia sin claves, transcripciones o respuestas. Separa los
resultados de laboratorio de cualquier afirmación de producción. Si cambia el
ciclo de vida de PortAudio, prueba Ctrl-C durante reproducción y documenta que
no hubo core dump ni audio residual.

## Fuera de la release por ahora

No presentar como incluidos ni validados:

- pruebas hardware-in-the-loop (HIL);
- datasets reales o grabaciones de replay;
- fotos o GIF pendientes en `docs/assets/`;
- control físico desde conversación;
- música, YouTube Music, Spotify o control de reproductores;
- AEC o barge-in validado para producción.
