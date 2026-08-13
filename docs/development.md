# Desarrollo

Use Python 3.12 or newer and install the development extras:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[cli,serial,dev]"
```

Para contribuir al laboratorio conversacional:

```bash
pip install -e ".[audio,vad,conversation,edge-tts,dev]"
sudo apt install ffmpeg
pytest tests/unit/audio tests/unit/conversation tests/unit/cli -q
```

La instalación no necesita una cuenta cloud ni abre dispositivos. Para una
prueba live, copia `config/conversation.env.example` fuera del repositorio y
consulta [conversation.md](conversation.md). Nunca uses claves reales en
fixtures, pruebas ni documentación.

For USB camera perception, install the optional extra and obtain YuNet
explicitly:

```bash
pip install -e ".[perception]"
sirah-models yunet --destination models/yunet
```

The model is checksum-verified and ignored by Git. Do not make runtime startup
download models or require a camera in CI.
