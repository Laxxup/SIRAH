# Desarrollo

Usa Python 3.12 o superior (la versión recomendada es 3.12, la misma que CI) e
instala los extras de desarrollo:

```bash
uv sync --extra cli --extra serial --extra dev
```

Para contribuir al laboratorio conversacional:

```bash
uv sync --extra audio --extra vad --extra conversation --extra edge-tts --extra dev
sudo apt install ffmpeg
uv run pytest tests/unit/audio tests/unit/conversation tests/unit/cli -q
```

La instalación no necesita una cuenta cloud ni abre dispositivos. Para una
prueba live, copia `config/conversation.env.example` fuera del repositorio y
consulta [conversation.md](conversation.md). Nunca uses claves reales en
fixtures, pruebas ni documentación.

Para percepción con cámara USB, instala el extra opcional y obtén YuNet
explícitamente:

```bash
uv sync --extra perception
uv run sirah-models yunet --destination models/yunet
```

El modelo se verifica por checksum y Git lo ignora. No hagas que el arranque
del runtime descargue modelos ni exija cámara en CI.