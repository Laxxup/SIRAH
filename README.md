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

## Pre-alpha local 0.1.0.dev0

La distribución `sirah`, importable como `sirah`, demuestra actualmente:

- conversación escrita con un proveedor de inteligencia intercambiable;
- contexto presente limitado y no persistente;
- decisiones estructuradas de Gemini mediante el SDK `google-genai`;
- catálogo y política local de capacidades;
- ejecución real a través de SIRAH Cortex `0.1.0a1`;
- un `RobotPort` simulado, determinista y sin hardware.
- percepción de presencia simulada a través de eventos públicos de Cortex;
- iniciativa de saludo determinista y TTS simulado cancelable;
- router local prioritario para órdenes exactas de parada.

`robot.home` y `robot.stop` son las capacidades garantizadas. `arm.greet` está
implementada de forma provisional reutilizando el plan mecánico existente en
Cortex; depende de API provisional y puede cambiar durante la serie pre-alpha.
Gemini propone una capacidad nominal, pero nunca crea `RobotCommand`, accede a
`RobotPort` ni decide grados, PWM, GPIO, canales o límites.

La versión base funciona sin Gemini:

```bash
python -m pip install .
python examples/offline_conversation.py
```

Gemini es opcional:

```bash
python -m pip install ".[gemini]"
export GEMINI_API_KEY="valor-configurado-fuera-del-repositorio"
export SIRAH_GEMINI_MODEL="gemini-3.6-flash"  # opcional
```

Si existen ambas claves, `GEMINI_API_KEY` tiene precedencia sobre
`GOOGLE_API_KEY`. La disponibilidad, las cuotas y los modelos dependen del
proyecto de Google. Consulta [la guía operativa de Gemini](docs/gemini.md).

## SIRAH Laboratory Console

La consola de laboratorio es una demostración interactiva textual, no una
interfaz definitiva ni un servidor. Conserva una sesión en memoria, permite
seleccionar el fake o Gemini y muestra la separación entre conversación,
propuesta, validación y ejecución:

```bash
.venv/bin/python examples/interactive_conversation.py --help
.venv/bin/python examples/interactive_conversation.py
.venv/bin/python examples/interactive_conversation.py --enable-greet
```

Comandos locales: `/ayuda`, `/estado`, `/componentes`, `/capacidades`,
`/contexto`, `/eventos`, `/limpiar`, `/presencia [clave]`, `/ausencia`,
`/evaluar`, `/silencio [on|off]`, `/autonomia [on|off]`, `/detener`,
`/voz-fin` y `/salir`. Las órdenes exactas `stop`, `para` y `detente` también
se resuelven localmente antes de la inteligencia. No llegan al proveedor ni
controlan hardware directamente.

La demostración actual reconoce un cuerpo simulado y señala cámara,
micrófono, altavoz, memoria persistente y hardware físico como no configurados.
La ausencia de esos componentes no impide conversar por texto ni ejecutar las
capacidades permitidas sobre el robot simulado.

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

| Área | Estado | Validación | Evidencia local |
|---|---|---|---|
| Texto, contexto y Cortex simulado | Implementado en pre-alpha | Validado sin red | `src/sirah/`, `tests/`, `examples/` |
| Gemini por texto | Implementado, opcional | Validado con dobles; smoke vivo opt-in | `src/sirah/gemini.py` |
| Conversa por texto | Implementado | Fake determinista y consola | `examples/interactive_conversation.py` |
| Contexto de sesión | Implementado | Memoria temporal acotada | `src/sirah/context.py` |
| Cortex | Implementado | API real `sirah-cortex==0.1.0a1` | `src/sirah/cortex_integration.py` |
| Robot simulado | Implementado | `RobotPort` y eventos observables | `src/sirah/simulated_robot.py` |
| Percepción simulada | Simulado | Evento público y WorldState de Cortex | `SimulatedPerception` |
| Iniciativa de saludo | Implementado, determinista | Política local con cooldown | `evaluate_initiative` |
| TTS | Simulado | Registra texto, sin audio real | `FakeSpeechOutput` |
| Brazo simulado | Provisional | Solo con `--enable-greet` | `arm.greet` |
| Cámara | No configurada | Sin implementación | `perception.camera` |
| Micrófono | No configurado | Sin implementación | `input.microphone` |
| Altavoz | No configurado | Sin implementación | `output.speaker` |
| Memoria persistente | No configurada | Sin SQLite ni archivos | `memory.persistent` |
| Hardware real | No configurado | Sin firmware o transporte | `robot.physical` |
| Saludo Velxio con un servo | Experimental | Validado en simulación | `experiments/velxio/greet_person_preview/` |
| Controlador facial ESP32/PCA9685 | Planeado | No validado | Inventario proporcionado por el equipo |
| ESP32-CAM | Planeado | No validado | Sin implementación local encontrada |
| Conversación (STT/LLM/TTS) | Planeado | No validado | Sin implementación local encontrada |
| Visión y percepción | Planeado | No validado | Sin implementación local encontrada |

El experimento Velxio procede del commit de Cortex
`ea10d96f3a58cb6b6ccde4ab01bc7ac7ac32c52f` y fue preservado en este
repositorio por el commit `8462538c0293a03375b9479a99f51e2d240b2495`. Sus
seis artefactos ejecutables y de simulación coinciden por SHA-256; el README de
esta copia es deliberadamente más completo y constituye su documentación
autoritativa.

No existe firmware estable para siete servos, Vosk, Piper, cámara, MQTT o
Serial concreto. Gemini existe únicamente como integración textual opcional;
no se presentan voz, visión o hardware real como implementados.

## Hardware conocido

El inventario declara un ESP32, un PCA9685 y siete servos faciales. El mapa de
canales conocido está documentado en
[`docs/components/face-controller.md`](docs/components/face-controller.md).
No existe evidencia local de validación física ni calibraciones.

## Navegación

- `docs/architecture/`: decisiones y límites transversales.
- `docs/components/`: inventario comprobable y estado de componentes.
- `docs/history.md`: evolución desde el prototipo experimental.
- `src/sirah/`: aplicación pre-alpha y sus límites de autoridad.
- `tests/`: pruebas normales sin red.
- `examples/`: demostración offline y smoke Gemini opt-in.
- `experiments/`: prototipos sin promover a integración estable.
- `docs/roadmap.md`: trabajo activo y criterios de promoción.

No existen todavía paquetes de voz, visión, firmware, GUI ni hardware porque
no hay implementaciones que demuestren esas responsabilidades.

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
