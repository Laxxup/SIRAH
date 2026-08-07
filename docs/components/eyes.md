# Ojos: seguimiento de cara y parpadeo natural

- Estado: Experimental probado (evidencia 2026-08-06)
- Hardware: ESP32 + servo horizontal (pin 25) + párpados izquierdos (pins 33/23) + Logitech C270 (usb 1-1, `/dev/video2`)
- Firmware: `firmware/sirah-eyes/sirah-eyes.ino`

## Propósito

Los ojos de SIRAH siguen horizontalmente a la persona más cercana detectada por
MediaPipe y parpadean de forma natural. Es la primera expresión física real del
androide y la base del bucle "percibe → saluda → escucha → responde".

## Protocolo serial (115200 baud, ASCII, líneas con `\n`)

| Comando | Significado |
|---|---|
| `X <0-100>` | Posición horizontal (0 = izquierda, 50 = centro, 100 = derecha). Desactiva AUTO. |
| `AUTO 1` | Modo autónomo: miradas aleatorias + parpadeo natural (~6 s). |
| `AUTO 0` | Modo seguimiento: solo obedece `X` y parpadea. |
| `CENTER` | Vuelve suave al centro. |
| `BLINK` | Dispara un parpadeo inmediato (uso propuesto: al saludar). |
| `READY` | Healthcheck. Responde `OK <posX> AUTO=<0|1> BLINK=<0|1>`. |

El firmware mantiene las animaciones naturales como modo `AUTO 1` (la
autonomía nativa del ojo), y las desactiva temporalmente al recibir `X` para
que el seguimiento tenga prioridad.

## Evidencia local (2026-08-06)

- Pipeline completo probado end-to-end: Cámara C270 (`/dev/video2`) → MediaPipe
  (`face_landmarker.task` en `/home/laxxup/models`) → mapeo `face_x` normalizado
  → servo `X` (con mirror + suavizado 0.25) → serial al ESP32.
- `READY` respondió `OK 52 AUTO=1 BLINK=0`; los comandos `X`/`AUTO` se recibieron.
- 500 muestras de log + 41 frames anotados en `/tmp/sirah-evidence/`
  (`eye_log.csv`, `frame_*.jpg`).
- Durante una prueba previa con cara presente, `face_x` varió de 0.81 a 0.71
  mientras el servo respondía de `X 19` a `X 29` (tracking funcional).
- Servidor captura del parpadeo natural (~6 s) y attach/detach de PWM para evitar
  zumbido, preservados intactos.

## Calibración de fábrica (firmware)

```
X_LEFT=14  X_CENTER=55  X_RIGHT=90     // ojo horizontal (grados)
PII_OPEN=90  PII_CLOSE=30               // párpado inferior izquierdo
PSI_OPEN=105 PSI_CLOSE=155              // párpado superior izquierdo
```

## Integración pendiente en el runtime

Hoy el seguimiento es un script independiente (`scripts/eye_follow_evidence.py`).
Para que SIRAH ande sola queda pendiente integrarlo como componente del runtime:

- Nuevo puente serial en `src/sirah/bridge/eye_controller.py` (reutiliza
  `pyserial-asyncio`, extra `bridge-serial`). Debe respetar la autoridad del
  runtime: solo el runtime abre el puerto serie, nunca un cliente web.
- `SIRAH_RUNTIME_SERIAL_DEVICE` (allowlist del runtime) para elegir el puerto;
  `SIRAH_RUNTIME_EYES` para armar/desarmar los ojos (hardware arranca desarmado).
- Componente en `sirah.registry` con estado `ready`/`degradado`; caída del serie
  degrada ojos pero el runtime y la conversación continúan.
- Ensamblaje en `SirahRuntime.start/stop` y conexión con la posición de la cara
  del `VisionLoop` (`latest_face_center_x` normalizado).
- Test determinista con transporte serie fake (sin hardware), cubriendo mapeo,
  mirror, degradación y no movimiento cuando está desarmado.
- Documentar permisos de puerto serie (`dialout`) y una regla udev para
  `/dev/ttyUSB*` / `/dev/ttyACM*` estable.

## Seguridad

- El puerto serie solo se configura en el entorno del servidor. Web Lab y CLI no
  pueden seleccionar puertos, ángulos ni rutas de firmware.
- Los servos están desarmados por defecto; el runtime los mueve solo con
  `SIRAH_RUNTIME_EYES=1`.
- Toda orden de movimiento pasa por la política del runtime antes de tocar
  hardware (límite establecido; el endurecimiento de CapabilityPolicy → Cortex
  para ángulos queda para la fase de cuerpo físico).

## Próximos pasos

1. Integrar el controlador de ojos en `SirahRuntime` (depende de que la cámara
   esté integrada: ver `src/sirah/perception/mediapipe_vision.py`).
2. Disparar un `BLINK` al saludar en el bucle autónomo `ve → saluda → escucha →
   responde`.
3. Ampliar el protocolo con verticalidad (`Y`) y ojos derechos cuando exista el
   hardware.
4. Smoke físico: dejar el runtime corriendo y verificar que los ojos siguen a
   una persona real, saludan con blink, parpadean solos y nunca zumban en reposo.
