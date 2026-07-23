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

SIRAH compone conversación, visión y dispositivos sobre SIRAH Cortex. Cortex
conserva el núcleo determinista y se comunica con adaptadores mediante
`RobotPort`; los adaptadores traducen hacia firmware y hardware. El mecanismo
técnico de integración entre ambos repositorios sigue pendiente.

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

No se encontró evidencia local de firmware estable para siete servos, Gemini,
Vosk, Piper, cámara, MQTT o Serial concreto. No se presentan como
implementados.

## Hardware conocido

El inventario declara un ESP32, un PCA9685 y siete servos faciales. El mapa de
canales conocido está documentado en
[`docs/components/face-controller.md`](docs/components/face-controller.md).
No existe evidencia local de validación física ni calibraciones.

## Navegación

- `docs/architecture/`: decisiones y límites transversales.
- `docs/components/`: inventario comprobable y estado de componentes.
- `docs/history.md`: evolución desde el prototipo experimental.
- `experiments/`: prototipos sin promover a integración estable.
- `docs/roadmap.md`: trabajo activo y criterios de promoción.

No existen todavía `src/`, `subsystems/`, `adapters/` ni `firmware/` porque no
hay implementaciones estables que demuestren esas responsabilidades.

## Decisiones abiertas

- forma de integrar SIRAH con Cortex;
- topología de procesos y equipos (PC, Raspberry Pi, ESP32);
- protocolos Serial, MQTT o HTTP;
- estructura de software y lenguajes;
- validación eléctrica, mecánica y de seguridad del controlador facial;
- adquisición y procesamiento de imágenes;
- proveedores y arquitectura de conversación.
