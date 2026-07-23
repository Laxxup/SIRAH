# Contribuir a SIRAH

Antes de promover código, documenta propósito, entradas, salidas, seguridad y
evidencia de validación. Usa nombres de código y carpetas en inglés.

Estados permitidos: Planeado, Experimental, En desarrollo, Implementado y
Deprecado. `Bloqueado` es una anotación adicional. La validación se declara
como No validado, Validado en simulación o Validado en hardware.

Los prototipos nacen en `experiments/` con objetivo, procedimiento, resultado y
decisión. Una responsabilidad estable justifica entonces `subsystems/`, un
cliente concreto justifica `adapters/`, y código realmente cargado en un
microcontrolador justifica `firmware/`.

Nunca conectes un LLM directamente con GPIO, PWM, PCA9685 o servos. Toda
capacidad mecánica debe atravesar planificación, seguridad y `RobotPort` de
Cortex antes de que un adaptador la traduzca al firmware.

## Entorno y gates

SIRAH requiere Python 3.13 o posterior. Instala primero el wheel de SIRAH Cortex
`0.1.0a1` y luego el extra de desarrollo:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install /ruta/a/sirah_cortex-0.1.0a1-py3-none-any.whl
.venv/bin/python -m pip install -e ".[dev]"
```

Antes de cada commit funcional ejecuta:

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy src tests --ignore-missing-imports
.venv/bin/python -m pytest -q
git diff --check
```

La suite normal no debe acceder a la red. No registres claves, prompts
completos, conversaciones privadas ni respuestas locales sensibles. No hagas
push ni otra operación remota sin autorización explícita.
