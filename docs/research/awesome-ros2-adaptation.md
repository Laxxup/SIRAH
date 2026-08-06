# Adaptación de patrones de awesome-ros2

## Alcance

Se revisó `fkromer/awesome-ros2` en el commit `de33fce` (18 de agosto de
2023). El repositorio está archivado y contiene una lista de recursos, no una
arquitectura que SIRAH deba adoptar. Esta nota conserva las ideas útiles y
explica por qué no se incorpora ROS 2 directamente.

Fuente: <https://github.com/fkromer/awesome-ros2>.

## Patrones adoptados

### Calidad y pruebas

La referencia a ROS 2 Quality Assurance Guidelines propone tratar la calidad
como una responsabilidad explícita del paquete y validarla con CI. SIRAH lo
adapta a sus contratos asíncronos y fakes deterministas:

- cada responsabilidad nueva debe tener entradas, salidas, seguridad y
  evidencia de validación;
- `pytest`, `ruff`, `mypy` y `git diff --check` son gates locales;
- las pruebas no usan red, secretos, audio persistente ni hardware real;
- los límites de un adaptador se prueban en su borde, no mediante una
  dependencia real del proveedor.

Referencia: <https://github.com/ros-industrial/ros2_quality_assurance_guidelines>.

### Diagnóstico estructurado

La categoría `diagnostics` de la lista inspira una salida legible por máquina,
no una dependencia con mensajes ROS. SIRAH ya tenía `ComponentRegistry` y
`SystemSnapshot`; el Web Lab ahora expone cada componente en
`GET /api/status` bajo `diagnostics`:

```json
{
  "id": "core/orchestrator",
  "kind": "core",
  "name": "orchestrator",
  "status": "ready",
  "detail": "started"
}
```

Esto permite una consola o dashboard futuro sin duplicar `WorldState` ni
inventar otra fuente de verdad.

Referencia: <https://github.com/bponsler/diagnostics/tree/ros2-devel>.

### Límites y seguridad del protocolo

Las referencias a `ros2_fuzzer` y `aztarna` sugieren probar los bordes de
transporte como entradas hostiles. SIRAH aplica primero esa idea a
`EdgeMessage.from_json`: JSON inválido, objeto no-diccionario, `msg_id` vacío,
kind desconocido, payload no-diccionario, timestamp no numérico o no finito
son rechazados con `ValueError` tipado y estable.

Referencias:

- <https://github.com/aliasrobotics/ros2_fuzzer>
- <https://github.com/aliasrobotics/aztarna>

## Patrones reservados

### Lifecycle y modos

`system-modes` inspira los estados `UNINITIALISED`, `INITIALISING`, `READY`,
`DEGRADED`, `ERROR` y `SHUTDOWN` que ya existen en SIRAH. No se introduce una
segunda máquina de estados: las transiciones de seguridad y hardware siguen
siendo responsabilidad de Cortex.

Referencia: <https://github.com/micro-ROS/system_modes>.

### Web bridge

`rosbridge_suite` confirma el valor de separar transporte, protocolo y cliente.
SIRAH conserva Flask y sus contratos propios; el navegador nunca crea
`RobotCommand` ni salta `CapabilityPolicy`, Cortex, `ActionExecutor` o
`RobotPort`.

Referencia: <https://github.com/RobotWebTools/rosbridge_suite>.

### Replay y telemetría

`rosbag2` y `ros2_data_collection` sugieren replay y recolección validada, pero
SIRAH no grabará audio, frames, conversaciones ni prompts por defecto. El
próximo recorder deberá ser opt-in, redacted, con rotación y limitado a eventos
estructurados, latencias y cambios de estado.

Referencias:

- <https://github.com/ros2/rosbag2>
- <https://github.com/Minipada/ros2_data_collection>

## No adoptar ahora

- ROS 2, DDS, `rosbag2` y `rosbridge_suite`: duplicarían contratos y añadirían
  dependencias sin una necesidad de hardware o topología demostrada.
- Docker o cross-compilation ROS: cámara, ALSA, Piper y Pi requieren primero
  un perfil de despliegue reproducible propio.
- Webots: la simulación actual de percepción y robot es suficiente para probar
  seguridad lógica y contratos deterministas.
- Logging cloud: contradice las reglas actuales de privacidad hasta definir
  redacción, consentimiento y retención.

El repositorio externo queda como referencia de investigación en
`/tmp/opencode/awesome-ros2`; no forma parte del paquete ni del runtime de
SIRAH.
