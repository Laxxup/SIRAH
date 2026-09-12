# S.I.R.A.H.

**Sistema Inteligente Robótico de Asistencia Humana**

SIRAH es un robot conversacional que combina un LLM, voz, visión local y ojos animados mediante servos. Puedes hablar con él por texto desde la terminal, o en modo manos libres mediante micrófono y altavoz.

El proyecto está en desarrollo activo. El código es funcional, pero algunas integraciones físicas requieren pruebas manuales (HIL) que no bloquean el uso del software.

## Qué puede hacer

- **Conversación por texto:** habla con SIRAH escribiendo en la terminal. No necesitas cámara, micrófono ni hardware adicional.
- **Conversación por voz:** modo manos libres con micrófono, transcripción STT (Groq) y respuesta hablada (Piper TTS).
- **Visión local:** seguimiento facial con OpenCV y YuNet; los ojos del robot pueden mirar a la persona detectada.
- **Ojos animados:** seis servos SG90 controlados por ESP32 + PCA9685, con parpadeo, mirada y expresiones.
- **Memoria conversacional:** historial local por defecto; memoria persistente opcional mediante Zep.

Las capacidades se suman progresivamente: empiezas por texto y añades voz, visión o hardware según necesites.

## Estructura del proyecto

```
cmd/sirah/         — entrada principal (texto, voz, visión)
cmd/vision/        — utilidad manual de cámara
internal/sirah/    — agente, LLM, memoria, contexto y timeline
internal/voice/    — captura, VAD, STT, Piper y reproducción PCM
internal/vision/   — detección facial y seguimiento (OpenCV/YuNet)
internal/motion/   — traducción de acciones semánticas a comandos de firmware
internal/firmware/ — protocolo serial y transporte hacia el ESP32
firmware/          — sketch Arduino de producción y calibradores
scripts/           — generación de calibración, benchmark de voz, bridge Piper
models/            — modelo YuNet (versionado con checksum y licencia)
config/            — calibración canónica de ojos (TOML)
```

## Quick Start

Conversación por texto sin hardware:

```sh
git clone https://github.com/Laxxup/SIRAH.git
cd SIRAH
cp .env.example .env
# Edita .env y añade tu LLM_API_KEY
CGO_ENABLED=0 go run ./cmd/sirah
```

Escribe un mensaje y pulsa **Enter**. SIRAH responde en la terminal.
**Ctrl+C** o **Ctrl+D** cierra la sesión.

Solo necesitas:

- Go 1.27
- Una clave de API para un proveedor LLM OpenAI-compatible (Groq, OpenAI, etc.)

No necesitas OpenCV, Piper, micrófono, cámara ni ESP32 para empezar.

## Requisitos

### Para conversación por texto

- **Go 1.27** (según `go.mod`)
- **Clave LLM:** cualquier proveedor con API `/chat/completions` compatible con OpenAI

### Para voz (`-voice`)

Además del texto:

- **Groq API key** (para STT)
- **Piper TTS 1.7.0** y un modelo de voz `.onnx` + `.onnx.json`
- **`arecord`** (captura ALSA) y micrófono
- **`aplay`** (reproducción ALSA) o reproductor alternativo

Ver [docs/piper.md](docs/piper.md) para instalar Piper y colocar el modelo.

### Para visión (`VISION_ENABLED=true` o `-preview`)

- OpenCV 4 con headers de desarrollo (ruta por defecto)
- `pkg-config`, compilador C++11 y CGO habilitado
- Cámara USB con V4L2 y permisos de acceso
- Display gráfico si usas `-preview`

La ruta por defecto es OpenCV 4:

```sh
go run ./cmd/sirah -preview
```

OpenCV 5 es opcional mediante el build tag `opencv5`:

```sh
go run -tags opencv5 ./cmd/sirah -preview
```

### Para firmware/hardware

- Arduino CLI 1.5.1
- Core ESP32 3.3.11
- Librerías Adafruit BusIO 1.17.4 y PWM Servo Driver 3.0.3
- ESP32, PCA9685, 6 servos SG90, alimentación externa y masa común

Ver [firmware/README.md](firmware/README.md) para compilación y calibración.

## Configuración

Copia `.env.example` a `.env` y completa al menos `LLM_API_KEY`.

Las variables están organizadas en secciones:

| Sección | Variables clave | Requerido para |
|---|---|---|
| Basic conversation | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | Modo texto |
| Voice | `GROQ_API_KEY`, `PIPER_*`, `ARECORD_COMMAND` | Modo `-voice` |
| Vision | `VISION_ENABLED`, `VISION_MODEL` | Cámara y seguimiento |
| Memory | `ZEP_API_KEY` | Memoria entre sesiones |
| Hardware | `FIRMWARE_SERIAL`, `FIRMWARE_BAUD` | ESP32 y servos |
| Advanced | `VOICE_*` | Afinación del VAD |

### Proveedor LLM

SIRAH espera un endpoint compatible con OpenAI (`/chat/completions`, Bearer token, streaming SSE). El ejemplo por defecto apunta a OpenCode Go, pero funciona con Groq, OpenAI u otros. Algunos proveedores no soportan `response_format.type=json_schema` o `reasoning_effort`; si usas uno de ellos, es posible que necesites ajustar la configuración.

### Visión opt-in

Visión está **desactivada por defecto**. Para activarla:

```sh
VISION_ENABLED=true go run ./cmd/sirah
```

O usa `-preview` para abrir también la ventana de depuración de OpenCV.

### Hardware opt-in

Deja `FIRMWARE_SERIAL` vacío para operar sin ESP32. SIRAH continúa conversando; simplemente no mueve los servos físicos.

## Uso

### Modo texto (default)

```sh
CGO_ENABLED=0 go run ./cmd/sirah
```

Cada línea de stdin es un turno. La respuesta aparece en stdout.

### Modo voz

```sh
go run ./cmd/sirah -voice
```

SIRAH escucha continuamente, transcribe, responde y habla.

### Preview de visión

```sh
go run ./cmd/sirah -preview
```

Muestra ventana de cámara con detecciones. Q cierra.

### Self-test de hardware

```sh
go run ./cmd/sirah -selftest
```

Requiere ESP32 configurado en `FIRMWARE_SERIAL` y una cámara. Mueve servos; no lo ejecutes sin hardware conectado.

### Debug

```sh
go run ./cmd/sirah -debug
```

Imprime métricas de red, tiempos y diagnósticos. No uses `-debug` con datos personales sensibles.

## Desarrollo y validación

```sh
make check          # tests headless, vet, calibración, checksum YuNet, tests C++ host
make check-opencv   # tests + race + vet + build con OpenCV 4 (ruta por defecto)
make check-opencv5  # tests + vet + build con OpenCV 5 (-tags opencv5, opcional)
make check-firmware # compilación Arduino del sketch de producción
```

`make check` no abre cámara, micrófono, altavoz ni puerto serial. Es seguro ejecutarlo en cualquier máquina.

## Limitaciones conocidas

- **OpenCV 4** es la ruta por defecto y la única validada por CI. **OpenCV 5** es opt-in mediante `-tags opencv5` y actualmente no se verifica automáticamente.
- **Piper TTS** requiere un modelo de voz externo (`.onnx` + `.onnx.json`). El repositorio no distribuye modelos de voz por cuestiones de licencia y tamaño.
- **Pruebas físicas (HIL)** del firmware y de la pose `tired` son manuales y pendientes. No bloquean la compilación ni los tests host.
- **Visión** es opt-in y requiere configuración explícita.
- **`go install github.com/Laxxup/SIRAH/cmd/sirah@latest`** todavía no representa una instalación completa porque el binario depende de assets externos (modelos, scripts Piper, `.env`) y de herramientas del sistema (Python, ALSA).

## Contribuir

Si quieres contribuir, consulta [CONTRIBUTING.md](CONTRIBUTING.md).
Ejecuta `make check` antes de enviar un cambio.

## Créditos

El mecanismo físico de los ojos de SIRAH está basado en el diseño original [**ε-Series Animatronic Eye Mechanism**](https://github.com/will-cogley/EyeMech_Epsilon) de **Will Cogley** / **NM Robotics**.
Las piezas impresas en 3D y el diseño mecánico pertenecen a su autor y conservan su licencia original ([CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)).

SIRAH añade sobre ese mecanismo su propio firmware, calibración, control de movimiento, seguimiento visual, voz, agente conversacional e integración de sistemas.

## Licencias

El código original de SIRAH está bajo MIT. Los diseños, modelos, librerías y assets de terceros conservan sus propias licencias:

- Mecanismo de ojos ε-Series Animatronic Eye Mechanism (Will Cogley / NM Robotics): CC BY-NC-SA 4.0
- Piper TTS 1.7.0: GPL-3.0-or-later
- Modelo YuNet: MIT (ver `models/LICENSE.yunet`)
- Librerías Arduino: según cada librería (BSD, MIT)
- Dependencias Go: según `go.mod` / `go.sum`

Consulta `LICENSE` para el texto completo y las referencias de procedencia.
