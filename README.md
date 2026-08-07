# SIRAH

**Sistema Inteligente Robótico de Asistencia Humana**

SIRAH es el sistema completo del robot: capacidades concretas, dispositivos,
protocolos, firmware, experimentos y documentación de integración. La
reconstrucción actual comienza de forma deliberadamente mínima y crecerá cuando
exista código real que justifique nuevas responsabilidades.

SIRAH Cortex es el núcleo determinista hermano. Posee dominio, eventos,
`WorldState`, comportamiento, planificación, seguridad, ejecución, tracking,
cancelación y emergencia. SIRAH utilizará Cortex; Cortex no dependerá de este
repositorio.

SIRAH compone conversación, percepción y dispositivos sobre SIRAH Cortex.
Cortex conserva el núcleo determinista y se comunica con adaptadores mediante
`RobotPort`; los adaptadores futuros traducirán hacia firmware y hardware.

SIRAH es un agente robótico modular, no solamente un chatbot. Mantiene una
conciencia situacional operativa limitada: representa el contexto actual, los
componentes disponibles, las capacidades habilitadas, el estado de Cortex y
los resultados recientes. Esto no describe conciencia humana, sentiencia ni
experiencia subjetiva.

## Pre-alpha local 0.2.0.dev0

La distribución `sirah`, importable como `sirah`, demuestra actualmente:

- conversación escrita con un proveedor de inteligencia intercambiable;
- contexto presente limitado y no persistente;
- decisiones estructuradas mediante proveedores fake, laboratorio, Groq u
  Ollama;
- catálogo y política local de capacidades;
- ejecución real a través de SIRAH Cortex `0.1.0a1`;
- un `RobotPort` simulado, determinista y sin hardware.
- percepción de presencia simulada a través de eventos públicos de Cortex;
- iniciativa de saludo determinista y TTS simulado cancelable;
- TTS local Piper experimental, opcional y degradable, mediante API Python con
  modelo persistente por ciclo de vida del runtime;
- entrada Whisper experimental desde el Web Lab y proveedores fake para tests;
- percepción Haar experimental con cámara local y `SimulatedPerception`;
- Web Lab Flask con diagnóstico de micrófono, autonomía visible y snapshot de
  componentes;
- router local prioritario para órdenes exactas de parada.

`robot.home` y `robot.stop` son las capacidades garantizadas. `arm.greet` está
implementada de forma provisional reutilizando el plan mecánico existente en
Cortex; depende de API provisional y puede cambiar durante la serie pre-alpha.
Groq y Ollama proponen decisiones estructuradas, pero nunca crean
`RobotCommand`, acceden a `RobotPort` ni deciden grados, PWM, GPIO, canales o
límites.

La versión base funciona sin un proveedor externo:

```bash
python -m pip install .
.venv/bin/python -m pytest -q
```

## Runtime Headless

`sirah-runtime` es el proceso servidor que ensambla `SirahRuntime` y posee el
socket Unix y las configuraciones de dispositivos. CLI y Web Lab son clientes;
no pueden elegir dispositivos ni crear el runtime. Piper es opcional y solo se
configura aquí; no añade cámara, autonomía, UI, Telegram ni control físico.

Configura únicamente en el entorno del servicio, nunca en una petición cliente:

```bash
export SIRAH_RUNTIME_SOCKET=/run/sirah/runtime.sock
export SIRAH_RUNTIME_CLI_SECRET="secreto-fuera-del-repositorio"
export SIRAH_RUNTIME_WEB_LAB_SECRET="secreto-fuera-del-repositorio"
export SIRAH_RUNTIME_PROFILE=dev_laptop
export SIRAH_RUNTIME_CAPTURE_DEVICES=default
export SIRAH_RUNTIME_CAPTURE_DEVICE=default
export SIRAH_RUNTIME_OUTPUT_DEVICES=default
export SIRAH_RUNTIME_OUTPUT_DEVICE=default
# Opcional tras instalar `.[voice-piper]`; ambos son archivos externos legibles.
export SIRAH_RUNTIME_PIPER_MODEL=/opt/sirah-voices/es_MX-voice.onnx
export SIRAH_RUNTIME_PIPER_CONFIG=/opt/sirah-voices/es_MX-voice.onnx.json
.venv/bin/sirah-runtime
```

El proceso valida que el socket sea absoluto, que ambos secretos existan, que el
perfil sea `dev_laptop` o `dev_distributed`, y que los dispositivos configurados
pertenezcan a sus allowlists. La salida configurada queda validada y reservada
para el runtime. Si se configuran ambos archivos Piper, el runtime carga una
voz una sola vez con `piper-tts`; síntesis y reproducción por la salida
permitida permanecen separadas. Un fallo de Piper degrada voz y conserva el
runtime textual. `SIGINT` y `SIGTERM` detienen ordenadamente el runtime y
eliminan su socket propio.

El diseño de systemd está en
[`deploy/systemd/sirah-runtime.service`](deploy/systemd/sirah-runtime.service).
El script `scripts/deploy_pi.sh` requiere una copia del proyecto en `/opt/sirah`
(o `SIRAH_INSTALL_DIR`) y un host que ya provea `python3.14`; no sustituye ese
requisito por el Python del sistema. La evidencia histórica de Raspberry Pi con
Debian 13 y Python 3.13 no es un objetivo de despliegue soportado para esta
versión. El script instala el paquete y las unidades del runtime y del Web Lab
local opcional. Solo prepara los archivos: no habilita ni inicia servicios.
Copia los ejemplos a `/etc/sirah/*.env.example`; crea los
archivos privados `runtime.env` y, si corresponde, `web-lab.env` con permisos
`0600` y secretos reales antes de habilitar unidades manualmente.

Los clientes reciben únicamente el socket y su secreto compartido. La consola
usa `SIRAH_CLI_SECRET`; Web Lab usa `SIRAH_WEB_LAB_SECRET`. Estos nombres son
deliberadamente distintos de `SIRAH_RUNTIME_CLI_SECRET` y
`SIRAH_RUNTIME_WEB_LAB_SECRET`, que pertenecen al entorno privado del runtime:

```bash
# En otra terminal, tras iniciar sirah-runtime.
export SIRAH_RUNTIME_SOCKET=/run/sirah/runtime.sock
export SIRAH_CLI_SECRET="el-mismo-secreto-configurado-para-cli"
.venv/bin/sirah-console

# Cliente Web Lab local opcional, sin configuración de dispositivos.
export SIRAH_RUNTIME_SOCKET=/run/sirah/runtime.sock
export SIRAH_WEB_LAB_SECRET="el-mismo-secreto-configurado-para-web-lab"
.venv/bin/sirah-web
```

Groq es opcional:

```bash
python -m pip install ".[groq]"
export GROQ_API_KEY="valor-configurado-fuera-del-repositorio"
export SIRAH_GROQ_MODEL="llama-3.3-70b-versatile"  # opcional
```

Ollama puede ejecutarse localmente con el extra `ollama`. La disponibilidad,
las cuotas y los modelos dependen del proveedor. La suite de tests usa
`laboratory` o `fake` y no accede a la red.

## SIRAH Laboratory Console

La consola de laboratorio es un cliente textual del runtime, no una interfaz
definitiva ni un servidor. Muestra la separación entre conversación, propuesta,
validación y ejecución sin crear el sistema ni seleccionar dispositivos:

```bash
SIRAH_RUNTIME_SOCKET=/run/sirah/runtime.sock \
SIRAH_CLI_SECRET="el-mismo-secreto-configurado-para-cli" \
.venv/bin/sirah-console
```

El runtime conserva el texto como ruta predeterminada. La voz local existente
usa una configuración de captura propiedad del servidor y no persiste audio.
Piper no forma parte del contrato de clientes: Web Lab y consola no pueden
habilitarlo ni cambiar modelo, configuración o salida.

## SIRAH Web Lab

El laboratorio web es un cliente local opcional del runtime. Expone conversación
y estado mediante el socket Unix; no crea cámara, selecciona dispositivos ni
recibe configuración de hardware. Inicia primero `sirah-runtime` y después el
cliente con su secreto compartido:

```bash
SIRAH_RUNTIME_SOCKET=/run/sirah/runtime.sock \
SIRAH_WEB_LAB_SECRET="el-mismo-secreto-configurado-para-web-lab" \
.venv/bin/sirah-web
```

Abre `http://localhost:5000`. El Web Lab no guarda conversaciones fuera del
contexto temporal del runtime. No incluye cámara, autonomía ni controles físicos
en esta fase.

## Historia del proyecto

SIRAH es anterior a esta reconstrucción. Un
[prototipo experimental previo](https://gitlab.com/Laxxup/ipt-sirah) permitió
explorar conversación, visión, dispositivos, persistencia e interfaces y
obtener experiencia práctica sobre sus dependencias y límites.

El repositorio actual reconstruye el sistema con fronteras arquitectónicas más
explícitas. El núcleo determinista se desarrolla por separado como
[SIRAH Cortex](https://github.com/Laxxup/SIRAH-Cortex). El prototipo anterior es
una referencia histórica valiosa, no la arquitectura autoritativa ni evidencia
de que todas sus capacidades estén disponibles actualmente. La historia y las
reglas de recuperación de conocimiento se documentan en
[`docs/history.md`](docs/history.md).

## Estado actual

La iniciativa situacional usa presencia efímera: `presence_key` identifica una
observación simulada, no una persona. La memoria social mantiene saludos
pendientes y confirmados con TTL de 600 segundos y un máximo de 128 entradas.
El saludo se confirma únicamente cuando el proveedor de TTS informa reproducción
completada. `PresentSystem` proyecta `InteractionMemory`; no mantiene otra
fuente de verdad.

`interaction.greet` es interacción vocal; `arm.greet` es un gesto mecánico
opcional y no se ejecuta implícitamente.

| Área | Estado | Validación | Evidencia local |
|---|---|---|---|
| Texto, contexto y Cortex simulado | Implementado en pre-alpha | Validado sin red | `src/sirah/core/`, `tests/` |
| Inteligencia fake/laboratorio | Implementado | Dobles deterministas y suite offline | `src/sirah/intelligence/` |
| Groq y Ollama por texto | Implementado, opcional | Adaptadores opt-in; no se usan en tests | `src/sirah/intelligence/` |
| Conversación por texto | Implementado | Consola, Web Lab y fakes | `src/sirah/core/orchestrator.py` |
| Contexto de sesión | Implementado | Memoria temporal acotada | `src/sirah/core/context.py` |
| Contrato Cortex | Integración preparada | API pública aislada por protocolo | `src/sirah/core/orchestrator.py` |
| Robot simulado | Implementado | `RobotPort` y políticas locales | `src/sirah/action/` |
| Percepción simulada | Simulado | Frames deterministas sin hardware | `src/sirah/perception/simulated.py` |
| Iniciativa y autonomía | Implementado, experimental | Política local y pruebas offline | `src/sirah/autonomy/` |
| TTS fake | Simulado | Determinista, sin audio real | `FakeSpeechOutput` |
| Piper TTS | Implementado, experimental | API opcional, modelo persistente y smoke físico opt-in; no universal | `docs/piper.md` |
| Brazo simulado | Provisional | Solo con `--enable-greet` | `arm.greet` |
| Cámara laptop | Experimental implementada | Smoke local; MediaPipe Tasks opt-in y Haar fallback | `src/sirah/autonomy/vision_loop.py` |
| Micrófono | Experimental | Diagnóstico `arecord`; navegador requiere permiso y `ffmpeg`/Whisper | `src/sirah/web_server.py` |
| Altavoz del robot | No configurado | La prueba Piper usó audio local externo | `output.speaker` |
| Memoria persistente | No configurada | Sin SQLite ni archivos | `memory.persistent` |
| Hardware real | No configurado | Sin firmware o transporte | `robot.physical` |
| Saludo Velxio con un servo | Experimental | Validado en simulación | `experiments/velxio/greet_person_preview/` |
| Controlador facial ESP32/PCA9685 | Planeado | No validado | Inventario proporcionado por el equipo |
| ESP32-CAM | Planeado | No validado | Sin implementación local encontrada |
| Entrada de voz (STT) | Implementado, experimental | Whisper Web Lab; micrófono depende de permisos y dispositivos | `src/sirah/voice/stt_whisper.py` |
| Visión y percepción | Experimental implementado | Simulación, MediaPipe Tasks/Haar y smoke local; color/sonrisa/manos | `src/sirah/perception/mediapipe_vision.py` |

El experimento Velxio procede del commit de Cortex
`ea10d96f3a58cb6b6ccde4ab01bc7ac7ac32c52f` y fue preservado en este
repositorio por el commit `8462538c0293a03375b9479a99f51e2d240b2495`. Sus
seis artefactos ejecutables y de simulación coinciden por SHA-256; el README de
esta copia es deliberadamente más completo y constituye su documentación
autoritativa.

No existe firmware estable para siete servos, cámara, MQTT o Serial concreto.
Whisper existe como adaptador PTT experimental sin modelo incluido; Piper usa su
API Python opcional con modelo externo y reproducción separada propiedad del
runtime. La síntesis y reproducción se validaron en una configuración Debian 13
concreta.
Groq y Ollama son integraciones textuales opcionales. La entrada Whisper no
constituye conversación manos libres ni valida micrófono, visión o hardware
robótico real.

## Hardware conocido

El inventario declara un ESP32, un PCA9685 y siete servos faciales. El mapa de
canales conocido está documentado en
[`docs/components/face-controller.md`](docs/components/face-controller.md).
No existe evidencia local de validación física ni calibraciones.

## Navegación

- `docs/architecture/`: decisiones y límites transversales.
- `docs/components/`: inventario comprobable y estado de componentes.
- `docs/research/awesome-ros2-adaptation.md`: patrones ROS 2 adaptados sin
  introducir ROS 2 en el runtime.
- `docs/research/vision-multiface.md`: evidencia y límites de la percepción
  multirostro, color y expresión.
- `docs/research/mediapipe-tasks-vision.md`: modelos locales, manos, blendshapes
  y restricciones de despliegue en Raspberry Pi 4B.
- `docs/history.md`: evolución desde el prototipo experimental.
- `src/sirah/`: aplicación pre-alpha y sus límites de autoridad.
- `tests/`: pruebas normales sin red.
- `scripts/`: comandos de demostración y despliegue locales.
- `experiments/`: prototipos sin promover a integración estable.
- `docs/roadmap.md`: trabajo activo y criterios de promoción.

No existen todavía wake word, AEC, escucha continua, firmware estable, GUI
definitiva ni hardware validado. STT cuenta con runtime Whisper PTT experimental
y TTS con contrato, fake y adaptador Piper.

## Decisiones abiertas

- topología de procesos y equipos (PC, Raspberry Pi, ESP32);
- protocolos Serial, MQTT o HTTP;
- estructura de software y lenguajes;
- validación eléctrica, mecánica y de seguridad del controlador facial;
- adquisición y procesamiento de imágenes;
- licencia declarada: Apache-2.0.

SIRAH se distribuye bajo Apache-2.0. SIRAH `0.1.0.dev0` sigue siendo
pre-alpha, no una API estable. No controla hardware real y no es software
certificado para seguridad funcional. Cortex y la política local mejoran la
seguridad lógica, pero no sustituyen firmware seguro, watchdog, alimentación
protegida, paro físico ni validación mecánica.
