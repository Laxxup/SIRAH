# Cómo usar SIRAH

SIRAH es un robot social de escritorio: ojos con servos que siguen tu cara,
parpadeo natural, micrófono, altavoz, cámara y voz. Este documento cubre cómo
ponerla a funcionar y qué hace cada pieza.

## Hardware conectado (laptop)

| Pieza | Dispositivo | Notas |
|---|---|---|
| Cámara | Logitech C270 (`/dev/video2`) | Montada bajo los ojos, detecta rostro/color/sonrisa |
| Micrófono | C270 USB Audio (`hw:1,0`) | Micrófono de la webcam |
| Altavoz | Laptop (`default`) | Salida analógica PCH |
| Ojos (servos) | ESP32 (`/dev/ttyUSB0`) | Servo horizontal pin 25, párpados pines 33/23 |
| Voz TTS | Piper `es_ES-sharvard-medium` | Español, reproduce WAV por `aplay` |
| STT | Whisper `base` (faster-whisper) | Transcribe lo que dices |
| Inteligencia | Groq (Llama 3.3) o fallback echo | Conversación real si hay `GROQ_API_KEY` |

## Requisitos

- Python 3.14, entorno `.venv` en la raíz del proyecto.
- Modelos MediaPipe: `/home/laxxup/models/face_landmarker.task` y `hand_landmarker.task`.
- `arecord`, `aplay` (ALSA) instalados.
- Dependencias Python ya instaladas en `.venv` (mediapipe, faster-whisper, piper-tts,
  pyserial, pyserial-asyncio, flask, opencv).

```bash
# si faltan paquetes puntuales:
.venv/bin/python -m pip install pyserial pyserial-asyncio
```

Permisos de puerto serie (una sola vez, requiere logout tras aplicarlo):

```bash
sudo usermod -aG dialout $USER
```

## Componentes

### Firmware de los ojos — `firmware/sirah-eyes/`

`firmware/sirah-eyes/sirah-eyes.ino` corre en el ESP32. Animación: solo parpadeo
automático cada ~6s; el ojo horizontal **solo se mueve por comandos serial**.
Protocolo ASCII a 115200 baud:

| Comando | Efecto |
|---|---|
| `X <0-100>` | Mueve el ojo horizontal (0=izq, 50=centro, 100=der) |
| `CENTER` | Vuelve al centro |
| `BLINK` | Parpadeo inmediato |
| `READY` | Healthcheck → responde `OK <posX> BLINK=<0\|1>` |

Compilar y subir (Arduino CLI, paquete esp32:esp32 3.3.11 instalado):

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/sirah-eyes
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 firmware/sirah-eyes
```

### Laboratorio de voz — `scripts/sirah_voice_lab.py`

Es el programa principal. Ojos + micrófono + Whisper + inteligencia + Piper,
todo junto. SIRAH es **autoconsciente**: sabe la posición de sus ojos, si detecta
cara, el color de ropa, sonrisa, distancia e iluminación, y menciona ese estado
de forma natural al hablar. Sin `GROQ_API_KEY` usa un modo echo.

```bash
cd /home/laxxup/SIRAHv0.2

# Sin Groq (modo eco, sin conversación real):
set -a && . ./.env && set +a 2>/dev/null
PYTHONPATH="src" .venv/bin/python scripts/sirah_voice_lab.py

# Con Groq (requiere GROQ_API_KEY en el entorno):
export GROQ_API_KEY="sk-..."
PYTHONPATH="src" .venv/bin/python scripts/sirah_voice_lab.py

# Lanzador desacoplado (sobrevive a la terminal):
set -a && . ./.env && set +a && export PYTHONPATH="src" && \
setsid .venv/bin/python scripts/sirah_voice_lab.py \
  --camera /dev/video2 --serial /dev/ttyUSB0 --mic hw:1,0 --speaker default --mirror true \
  > /tmp/sirah-evidence/voice_lab.log 2>&1 < /dev/null &
```

Cada turno: graba 5s, transcribe, piensa, habla. Di "salir" para terminar.

Monitoreo:

```bash
pgrep -af sirah_voice_lab        # ¿está vivo?
tail -f /tmp/sirah-evidence/voice_lab.log   # ver en vivo
pkill -f sirah_voice_lab         # detener
```

Flags útiles: `--no-eyes` (sin servos), `--record-s 8` (grabaciones más largas),
`--mirror false` (invierte dirección del seguimiento), `--mic hw:0,0`
(micrófono del laptop en vez del de la webcam).

### Preview de ojos (sin voz) — `scripts/eyes_live_preview.py`

Solo muestra la cámara con el rectángulo de detección. Útil para verificar encuadre.

```bash
PYTHONPATH="src" .venv/bin/python scripts/eyes_live_preview.py --camera /dev/video2 --mirror true
```

## Cómo interactuar

1. Lanza `sirah_voice_lab.py`.
2. Ponte frente a la C270 (la cámara bajo los servos). Los ojos te seguirán
   horizontalmente; parpadean solos cada ~6 segundos.
3. Cuando la consola muestre `🎤 ESCUCHANDO`, habla. Whisper transcribe en español.
4. SIRAH piensa (Groq o eco) y responde con voz por el altavoz. Sus respuestas
   mencionan de forma natural lo que "ve" y "siente": posición de la mirada, color
   de ropa, sonrisa, distancia.
5. Di **"salir"** para cerrar.

## Bitácora y evidencia

Los logs y frames anotados se guardan en `/tmp/sirah-evidence/`:
`eye_log.csv`, `frame_*.jpg`, `voice_lab.log`.

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| Los ojos no se mueven | Serial ocupado o firmware viejo | Cierra Serial Monitor, sube `sirah-eyes.ino` v2 |
| "no face" siempre | Cámara mal enfocada o ángulo | Reclina la C270 hacia tu rostro, usa `eyes_live_preview.py` |
| Colores mal detectados (solo "azul") | Bug de ROI del torso (corregido) | Usa la versión actual de `mediapipe_vision.py` |
| No hay voz | `aplay` falla o modelo Piper falta | Verifica `es_ES-sharvard-medium.onnx` y `aplay -L` |
| Permiso denegado en `/dev/ttyUSB0` | Usuario sin grupo `dialout` | `sudo usermod -aG dialout $USER` + reiniciar sesión |
| El microfono no graba | Dispositivo incorrecto | Prueba `--mic hw:1,0` (C270) o `--mic hw:0,0` (laptop) |
| Delay alto en la cámara | Detección cada frame | El lab usa detección espaciada cada 3 frames |

## Próximos pasos

- Autonomía completa: integrar cámara + ojos + voz en `SirahRuntime` (headless).
- Wake word / escucha continua (fuera de alcance actual).
- Servos faciales (cara, boca) vía PCA9685/ESP32 cuando exista el hardware.
- Interfaz web (Web Lab) como consola de observación.
