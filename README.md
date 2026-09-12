# S.I.R.A.H.

### Sistema Inteligente Robótico de Asistencia Humana

SIRAH es un robot conversacional en desarrollo que combina voz, un LLM,
vision local y ojos animados mediante ESP32 + PCA9685.

## Estado

- Voz real, Groq STT, LLM streaming y Piper han funcionado juntos en pruebas
  manuales.
- La camara, YuNet y el seguimiento facial han funcionado en el host de
  desarrollo.
- El protocolo serial, Motion y la cardinalidad de acciones tienen tests.
- Los extremos finales de los seis servos fueron validados fisicamente durante
  calibracion. La integracion completa del runtime y la pose candidata `tired`
  siguen como **HIL PENDING** hasta confirmar tambien V+ sostenida.
- Las pruebas HIL adicionales son manuales y no son requisito para publicar el
  codigo, ejecutar los tests host ni compilar el firmware.
- El benchmark controlado de 20 turnos es **NOT RUN / INVALID TEST SETUP**. La
  latencia se observo baja en uso real, pero no se publica una mediana o p90.

## Arquitectura

```text
Mic -> VAD -> Groq STT -> Agent -> LLM streaming -> Piper -> aplay
Camera -> OpenCV/YuNet -> Perception -> Motion -> Serial -> ESP32 -> PCA9685
```

`BLINK` controla solo parpados y `TARGET` controla solo los ejes X/Y. Las
acciones se programan contra bytes PCM escritos al reproductor; eso no equivale
a una medicion de audio fisicamente audible.

## Requisitos

- Go 1.27, segun `go.mod`.
- Python 3.11 o posterior para los scripts que usan `tomllib`.
- GNU Make para los targets de verificacion y un compilador C++17 para los
  tests host del firmware.
- `piper-tts==1.7.0`, un modelo de voz compatible y `aplay` para iniciar el
  runtime actual. El modelo de voz no se versiona.
- OpenCV 5, o OpenCV 4 usando el build tag `opencv4`, `pkg-config`, un
  compilador C++11 y Linux/V4L2 para Vision.
- `arecord` y una clave Groq para el modo `-voice`.
- Arduino CLI 1.5.1, core ESP32 3.3.11 y las librerias indicadas en
  [firmware/README.md](firmware/README.md) solo para compilar el firmware.

Vision es opcional con `VISION_ENABLED=false`; el ESP32 es opcional dejando
`FIRMWARE_SERIAL` vacio; Zep es opcional dejando `ZEP_API_KEY` vacio. RNNoise
es una ruta experimental que requiere el build tag `rnnoise` y bibliotecas
nativas `rnnoise` y `soxr`.

Consulta [docs/piper.md](docs/piper.md),
[docs/vision-bridge.md](docs/vision-bridge.md) y
[firmware/README.md](firmware/README.md) para el setup especializado.

## Inicio Rapido

```sh
cp .env.example .env
# Completa LLM_API_KEY, configura Piper y añade GROQ_API_KEY para -voice.
go run -tags opencv4 ./cmd/sirah
```

OpenCV 5 usa el mismo comando sin `-tags opencv4`. Para compilar sin Vision:

```sh
CGO_ENABLED=0 VISION_ENABLED=false go run ./cmd/sirah
```

El modo manos libres se inicia con:

```sh
go run -tags opencv4 ./cmd/sirah -voice
```

Para la demo publica con preview:

```sh
go build -tags opencv4 -buildvcs=false -o sirah ./cmd/sirah
./sirah -voice -preview
```

## Configuracion Y Modos

`.env.example` documenta los servicios y rutas locales. El endpoint OpenCode Go
recibe automaticamente el `AGENT_SESSION_ID` requerido; otros proveedores
OpenAI-compatible no reciben headers especificos de OpenCode.

- Sin flags: conversacion por texto.
- `-voice`: conversacion manos libres.
- `-preview`: ventana de Vision; requiere display.
- `-debug`: diagnosticos, incluidas transcripciones; no usar con datos sensibles.
- `-selftest`: mantenimiento de hardware, no uso normal.

En `-voice`, `WAKEUP_TEXT` configura el saludo inicial; un valor vacio lo
desactiva. `NATURAL_BLINK_ENABLED=false` desactiva el parpadeo natural. La
animacion corporal comienza despues del primer write PCM y no retiene el audio.

Nunca versiones `.env`. Vision y firmware pueden desactivarse con
`VISION_ENABLED=false` y `FIRMWARE_SERIAL=` respectivamente.

## Desarrollo Y Validacion

```sh
make check
```

`make check` verifica formato Go sin reescribir archivos, modulos, tests y vet
sin CGO, calibracion generada, checksum de YuNet y tests C++ host. Para la ruta
OpenCV 4:

```sh
make check-opencv4
```

La compilacion Arduino permanece separada porque requiere su toolchain y
bibliotecas:

```sh
make check-firmware
```

Consulta el `Makefile` para ejecutar una comprobacion individual. Ninguno de
estos targets abre camara, microfono, altavoz o puerto serial. Compilar y
ejecutar tests host no constituye una prueba HIL.

## Hardware Y Seguridad

`firmware/sirah/` es el unico firmware de produccion. Los calibradores son
herramientas manuales y no hablan el protocolo Go. La calibracion canonica vive
en `config/eyes-calibration.toml`; no copies sus angulos a otro robot sin
recalibrar.

Usa alimentacion externa adecuada para los servos, masa comun y VCC logico
separado de V+. No ejecutes sweeps ni energices actuadores si V+ es inestable.
El firmware arranca centrado y abierto, sin coreografia autonoma, y no anuncia
`READY` cuando el PCA9685 no responde por I2C. El host coordina wake-up,
tracking y blink natural mediante acciones semanticas.

## Privacidad, Licencias Y Limitaciones

Segun `.env`, SIRAH puede enviar audio a Groq, texto al proveedor LLM e historial
a Zep. `-debug` imprime transcripciones. Revisa las politicas de cada servicio
antes de usar datos personales.

El codigo es MIT. Piper 1.7.0 es GPL-3.0-or-later y se instala externamente; cada
voz conserva su propia licencia. El modelo YuNet incluido es MIT. Las librerias
Arduino conservan sus licencias, incluida Adafruit PWM Servo Driver bajo BSD.
Consulta [LICENSE](LICENSE) y los documentos especializados para procedencia y
versiones. El tag `v3.28.0` de la dependencia Zep Go no declara una licencia en
su repositorio upstream; confirma sus terminos antes de distribuir binarios que
la incorporen.
