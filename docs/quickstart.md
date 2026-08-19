# Inicio rápido

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana**. Hay dos rutas
independientes: ojos con `FakeESP32` o hardware físico, y conversación por voz
en laboratorio. La conversación no mueve el robot.

Prerequisitos: `uv` (gestor de entornos y dependencias del proyecto) y
Python ≥ 3.12 en PC o Raspberry Pi 4.

## 1. Sin hardware — FakeESP32 (recomendado primero)

```bash
git clone https://github.com/Laxxup/SIRAH.git sirah
cd sirah
uv sync --extra cli --extra serial
uv run sirah-runtime --fake --eyes
```

Qué debe pasar: el runtime arma los ojos sobre el gemelo FakeESP32, mantiene
el heartbeat y termina limpiamente (exit 0) con Ctrl-C. Con `--verbose`
imprime al detener el estado final de cada componente (`[off] eyes: shutdown`
tras un apagado limpio). Un fallo de arranque degrada el componente
(DEGRADED) en vez de matar la app — compruébalo desarmando un componente.

Opciones útiles: `--verbose` para ver el registro de estados, `--fake`
selecciona el twin (ADR-0010), `SIRAH_EYES=0` desarma los ojos.

## 2. Con hardware real

Material (ver [pin-map.md](hardware/pin-map.md) y ADR-0011):

- ESP32 + PCA9685 (0x40) + rail de 6 servos + fuente externa 5 V con GND
  común (el ESP32 se alimenta por USB solo para lógica/flasheo).
- Cable USB-UART al dispositivo `/dev/ttyUSB0` (allowlist ADR-0002).

Una regla udev puede dar un nombre estable `/dev/sirah-eyes` (opcional; por
defecto se usa `/dev/ttyUSB0`). Sustituye `idVendor`/`idProduct` por los de tu
puente USB-UART; el ejemplo está en [pin-map.md](hardware/pin-map.md#serial-device-pc--esp32).

Flasha el firmware `firmware/sirah-eyes/platform/main.ino` (Arduino IDE o
plataforma CLI) y arranca:

```bash
uv run sirah-runtime --eyes
uv run sirah-runtime --eyes --device /dev/sirah-eyes   # o el nombre del puerto
```

## 3. Validar la calibración

```bash
uv run sirah-calibrate validate
```

Comprueba que `config/actuators.yaml` espeja sin divergencias
`firmware/sirah-eyes/config/calibration.h` y
`firmware/sirah-eyes/platform/pins.h` (ADR-0009).

## 4. Observar la visión (sin ojos)

Con una webcam USB y el modelo YuNet (extra opcional `[perception]`):

```bash
uv sync --extra cli --extra serial --extra perception
uv run sirah-models yunet --destination models/yunet
uv run sirah-perceive --camera-device /dev/video0 --yunet-model models/yunet/face_detection_yunet_2023mar.onnx
```

`--max-frames N` limita la duración (0 = hasta que la fuente termine) y
`--interval` fija el ritmo entre lecturas. El CLI imprime por frame el
objetivo normalizado (`face x=... y=... conf=... age=...`) o `no face`, más
un resumen de frescura: `frames`, `faces` y, si la fuente la instrumenta,
`captured`/`consumed`/`dropped` y `capture_fps` (`CameraStats`). No arma los
ojos ni abre el serial (ADR-0009). También acepta `--replay-jsonl` y
`--replay-video` como fuentes.

`uv run sirah-models` descarga y verifica el modelo por checksum antes de
guardarlo (Git ignora `models/`). Los umbrales del detector YuNet siguen los
valores de la clase de OpenCV Zoo (score `0.6`, nms `0.3`, top_k `5000`),
más permisivos que el default 0.9 de `cv2.FaceDetectorYN.create`; caras
pequeñas o lejanas aparecen y la capa de atención decide si importan.

## 5. Problemas frecuentes

| Síntoma | Causa probable | Fix |
|---|---|---|
| `device '...' not allowlisted` | El dispositivo no matchea la allowlist | Usar `/dev/ttyUSB*` o `/dev/sirah-eyes` |
| Falta PyYAML al cargar config | Extra `[cli]` no instalado | `uv sync --extra cli --extra serial` |
| `eyes: DEGRADED` al bootear | Serial ocupada o ESP32 sin flash | Cerrar otros programas, verificar cable |
| Servos no responden | Falta la fuente 5 V / brownout | Fuente externa + GND común (ADR-0011) |
| `sirah-perceive` entrega frames pero `faces=0` con la cámara encendida | La exposición automática de la webcam sobreexpone | Ajustar exposición a mano (p. ej. `v4l2-ctl --set-ctrl exposure=150,auto_exposure=1`) y volver a medir |

## 6. Conversación experimental por voz

El laboratorio conversacional no requiere ojos ni ESP32. Instala audio, VAD,
conversación y Edge TTS, además de `ffmpeg`:

```bash
uv sync --extra audio --extra vad --extra conversation --extra edge-tts
sudo apt install ffmpeg
mkdir -p ~/.config/sirah
cp config/conversation.env.example ~/.config/sirah/conversation.env
chmod 600 ~/.config/sirah/conversation.env
```

Completa Ollama y Groq en el archivo privado, cárgalo y abre la conversación:

```bash
set -a
source ~/.config/sirah/conversation.env
set +a
uv run sirah-conversation listen --live --stt-provider groq --tts-provider edge --lab
```

La ruta local usa Faster-Whisper y Kokoro; la ruta cloud probada en laboratorio
usa Groq para STT, Ollama para intención y Edge para voz. Consulta
[conversation.md](conversation.md) para privacidad, comandos, diagnóstico,
barge-in y límites acústicos.
