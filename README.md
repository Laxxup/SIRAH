# SIRAH

<p align="center">
  <img src="https://raw.githubusercontent.com/Laxxup/SIRAH/main/logo/sirah.png" width="260" alt="SIRAH">
</p>

<p align="center">
  <a href="https://www.facebook.com/profile.php?id=61592100517778&amp;locale=es_LA"><img src="https://cdn.simpleicons.org/facebook/1877F2" width="22" alt="Facebook de Comunidad Robótica ITCM"></a>
  &nbsp;
  <a href="https://www.instagram.com/comunidadrobotica.itcm/"><img src="https://cdn.simpleicons.org/instagram/E4405F" width="22" alt="Instagram de Comunidad Robótica ITCM"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-Apache--2.0-4B8BBE" alt="Apache 2.0">
  <img src="https://img.shields.io/badge/python-3.12%2B-3776AB" alt="Python 3.12 o superior">
  <img src="https://img.shields.io/badge/status-prototipo%20en%20desarrollo-6A5ACD" alt="Prototipo en desarrollo">
</p>

## Qué es SIRAH

SIRAH significa **Sistema Inteligente Robótico de Asistencia Humana**. Es un
proyecto universitario del Instituto Tecnológico de Ciudad Madero (ITCM),
desarrollado en el Taller de Robótica con colaboración del IPT de Tampico
Centro.

El proyecto integra electrónica, software, control e inteligencia artificial
para construir un robot humanoide educativo. Sigue en desarrollo: las funciones
experimentales no son capacidades listas para producción ni controlan el robot
sin supervisión.

## Estado actual

- Runtime Python con `asyncio`, protocolo PC ↔ ESP32 y `FakeESP32` para pruebas sin hardware.
- Subsistema ocular con mirada 2D, párpados, límites físicos y calibración.
- Laboratorio conversacional de manos libres con VAD local, STT local o Groq,
  Ollama y TTS local, Azure o Edge.
- Edge TTS entrega audio por streaming; el pipeline mide STT, Ollama, primer
  PCM y salida de audio mediante `--lab`.
- `SIRAH_OLLAMA_THINK=low` es una configuración de laboratorio para comparar
  el presupuesto de razonamiento cloud sin cambiar el contrato de respuesta.

La conversación no controla ojos, ESP32, servos ni otro hardware. El contrato
de acción permanece limitado a `none`; música, navegación y acciones físicas
no están implementadas.

## Inicio rápido

Sin hardware:

```bash
pip install -e ".[cli,serial]"
sirah-runtime --fake --eyes
```

Para conversación y sus requisitos locales, consulta
[docs/conversation.md](docs/conversation.md). Para probar la ruta cloud
validada en laboratorio:

```bash
pip install -e ".[audio,vad,conversation,edge-tts]"
sudo apt install ffmpeg
mkdir -p ~/.config/sirah
cp config/conversation.env.example ~/.config/sirah/conversation.env
# Edita el archivo privado con Ollama y Groq; nunca subas las claves.
set -a && source ~/.config/sirah/conversation.env && set +a
sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

Antes de conectar hardware físico, lee [docs/hardware/](docs/hardware/).

## Pruebas

```bash
uv run pytest -q
uv run ruff check src/sirah tests
uv run mypy src/sirah
```

También hay pruebas de firmware y protocolo:

```bash
make -C firmware/sirah-eyes/tests/host core_tests
make -C firmware/sirah-eyes/tests/host contract_checker
```

## Documentación

- [Inicio rápido: ojos y conversación](docs/quickstart.md)
- [Guía conversacional: instalación, configuración y diagnóstico](docs/conversation.md)
- [Línea base de latencia en laboratorio](docs/laboratory/voice-latency-baseline.md)
- [Arquitectura: runtime físico y laboratorio conversacional](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Prechecks de release](docs/release.md)
- [Hardware y calibración](docs/hardware/)
- [ADR](docs/adr/)
- [Contribuir de forma segura](CONTRIBUTING.md)

## Licencia

SIRAH se distribuye bajo [Apache License 2.0](LICENSE).

## Créditos de referencia

El mecanismo ocular toma como referencia conceptual el modelaje 3D de
[@WillCogley en YouTube](https://www.youtube.com/@WillCogley), autor de
[EyeMech epsilon 3.2](https://www.youtube.com/watch?v=bAvuMn8QTo4&t=186s).
EyeMech se licencia bajo
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
SIRAH no distribuye ni modifica sus modelos 3D, código, electrónica, archivos
de fabricación ni documentación: firmware, calibración y electrónica de SIRAH
son implementaciones independientes bajo Apache-2.0.
