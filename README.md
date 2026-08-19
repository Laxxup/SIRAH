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

**SIRAH** (Sistema Inteligente Robótico de Asistencia Humana) es un robot
humanoide educativo del [Instituto Tecnológico de Ciudad Madero](https://www.itcm.edu.mx/)
(ITCM), desarrollado en el Taller de Robótica con colaboración del IPT de
Tampico Centro. Este repositorio contiene el software: un runtime que controla
ojos con expresión, visión por cámara y un laboratorio conversacional por voz.

Es un **prototipo en desarrollo**. Lo estable se puede probar sin hardware;
lo experimental está marcado como tal y no controla el robot sin supervisión.

## Qué puede hacer hoy

| Área | Estado |
|---|---|
| Ojos: runtime Python + firmware ESP32 (mirada 2D, párpados, parpadeo, límites seguros) | Estable; calibración física verificada el 2026-08-09 |
| Protocolo PC ↔ ESP32 v1.0 y consistencia de calibración | Estable |
| Visión: cámara USB + YuNet, seguimiento de mirada, gestos y personas | Experimental; requiere cámara y modelos |
| Conversación por voz: VAD → STT → LLM → TTS, manos libres | Experimental; laboratorio opt-in |
| Música, navegación o acciones físicas desde conversación | No implementado |

La conversación **no controla ojos, ESP32, servos ni otro hardware**. Su
contrato de acción permanece limitado a `none`; visión y conversación son
laboratorio opt-in.

## Arquitectura

El sistema tiene dos caminos separados que comparten estado: los **ojos**
(runtime + firmware ESP32) y la **conversación** (audio + nube). La conversación
nunca envía comandos al hardware.

```text
Cámara USB → Percepción (YuNet) → Atención → Comportamiento → Runtime
                                                                    ↓
                                     Firmware ESP32 ← serial v1.0 ←┘
                                                                    ↓
                                                     PCA9685 → 6 servos
```

```text
Micrófono → VAD → STT (local/Groq) → ConversationCore → LLM (Ollama)
                                                             ↓
                                           TTS (Kokoro/Azure/Edge)
                                                             ↓
                                                         Bocina
```

La cámara publica el frame más reciente en un `FrameBroker`; los workers de
percepción lo procesan fuera del loop principal, así que la visión no bloquea
la conversación. El detalle está en [docs/architecture.md](docs/architecture.md).

## Hardware

| Componente | Para qué se usa | Cuándo es necesario |
|---|---|---|
| Python ≥ 3.12 y `uv` | Ejecutar el software | Siempre |
| ESP32 + PCA9685 + 6 servos + fuente 5 V externa + cable USB-UART | Ojos físicos | Solo para ojos reales |
| Webcam USB + modelo YuNet (se descarga con `sirah-models`) | Visión | Opcional |
| Micrófono y bocina (PortAudio) | Conversación por voz | Opcional |
| Ninguno | Probar con `FakeESP32`, replay y tests | Primer contacto |

## Instalación

Prerrequisitos: Python ≥ 3.12 y [`uv`](https://docs.astral.sh/uv/). No hace
falta una cuenta cloud ni hardware para instalar.

```bash
git clone https://github.com/Laxxup/SIRAH.git
cd SIRAH
uv sync --extra cli --extra serial
```

Los extras de `pyproject.toml` se instalan según lo que quieras usar:

| Extra | Qué instala | Para qué |
|---|---|---|
| `cli`, `serial` | runtime base + puerto serie | Ojos (con o sin hardware) |
| `perception` | OpenCV + numpy | Visión con cámara (YuNet) |
| `gesture` | MediaPipe | Gestos y personas (visión avanzada) |
| `audio`, `vad`, `conversation` | audio, VAD, validación | Conversación por voz |
| `local-tts`, `edge-tts` | voces locales / Edge | TTS |
| `dev` | pytest, ruff, mypy | Desarrollo y tests |

## Probar sin hardware (primero)

```bash
uv run sirah-runtime --fake --eyes    # ojos sobre el gemelo FakeESP32
uv run sirah-conversation replay tests/fixtures/conversation/approved.jsonl  # conversación offline
uv run pytest -q                      # toda la suite de pruebas
```

`uv run sirah-runtime --fake --eyes` arma los ojos sobre un gemelo in-memory
que espeja el firmware: mantiene el heartbeat y termina limpiamente (exit 0)
con Ctrl-C o SIGTERM. Con `--verbose` imprime al detener el estado final de
cada componente. No abre puerto serie ni mueve servos.

Con hardware (ojos físicos, visión con cámara o conversación en vivo) sigue
el [inicio rápido](docs/quickstart.md). Para la ruta cloud de conversación
necesitas una [configuración privada](docs/conversation.md) con las claves de
Ollama y Groq.

## Pruebas

```bash
uv run pytest -q
uv run ruff check .
uv run mypy
make -C firmware/sirah-eyes/tests/host core_tests
```

La explicación de cada suite está en [docs/testing.md](docs/testing.md).

## Documentación

Organizada por lo que buscas; el índice completo está en
[docs/](docs/README.md).

- **Empezar**: [inicio rápido](docs/quickstart.md) · [conversación](docs/conversation.md)
- **Entender**: [arquitectura](docs/architecture.md) · [hoja de ruta](docs/roadmap.md) · [ADR](docs/adr/)
- **Hardware**: [requisitos, cableado y calibración](docs/hardware/) · [protocolo v1.0](docs/components/protocol.md)
- **Desarrollar**: [entorno de desarrollo](docs/development.md) · [pruebas](docs/testing.md) · [release](docs/release.md) · [contribuir](CONTRIBUTING.md)

## Seguridad y privacidad

- Reporta vulnerabilidades según [SECURITY.md](SECURITY.md).
- El laboratorio conversacional puede enviar la transcripción final a
  proveedores cloud solo con `--live`. Qué se envía y qué se guarda está en
  [docs/privacy.md](docs/privacy.md).

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