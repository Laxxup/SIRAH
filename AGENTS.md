# Instrucciones para agentes de SIRAH

SIRAH es el agente robótico modular y conversacional. Depende de SIRAH Cortex;
Cortex conserva `WorldState`, eventos, seguridad y ejecución robótica. Nunca
modifiques Cortex ni dupliques sus modelos públicos.

## Antes de editar

Lee `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/`, las ADR, el módulo
afectado, sus pruebas y la consola de laboratorio. Confirma rama y worktree.
Revisa la API pública instalada de Cortex antes de añadir imports provisionales.

## Reglas de arquitectura

- Usa el `WorldState` de Cortex; no construyas una segunda copia.
- Mantén en SIRAH la memoria de interacción, iniciativa, silencio, autonomía y
  TTS.
- Toda capacidad mecánica atraviesa `CapabilityPolicy`, Cortex, seguridad,
  `ActionExecutor` y `RobotPort`.
- Gemini solo propone decisiones estructuradas; nunca crea comandos ni toca
  hardware.
- La percepción debe publicar eventos estructurados, no mutar estado.
- TTS no es `RobotPort`; usa su contrato propio y adaptadores simulados.
- No inventes cámara, audio, voz, visión, firmware, red o hardware.
- Distingue siempre implementado, simulado, parcial y planificado.

## Verificación

```bash
.venv/bin/python -m ruff check src tests examples
.venv/bin/python -m mypy src tests --ignore-missing-imports
.venv/bin/python -m pytest -q
.venv/bin/python -m build
git diff --check
```

La suite no usa red, Gemini real, secretos, `time.sleep` ni hardware. Inspecciona
wheel y sdist, y prueba la consola offline desde una instalación limpia cuando
sea posible.

## Cambios y seguridad

No guardes conversaciones, claves ni prompts completos. No hagas push, force
push, merge, tag, release ni operaciones remotas sin autorización explícita.
Actualiza documentación, pruebas y CHANGELOG con cada responsabilidad real.
Un cambio está terminado cuando sus gates pasan, su estado está documentado,
la ruta de seguridad es comprobable y no introduce capacidades teatrales.
