# Contributing

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (only in
Spanish, never translated). Gracias por contribuir al subsistema de ojos.

## Reglas básicas

1. **Testea antes de pedir review**: `pytest tests -q` debe pasar completo.
2. **Nunca rompas el contrato**: el protocolo v1.0 es una gramática
   cerrada; cualquier cambio requiere ADR y bump de versión del protocolo
   (`docs/components/protocol.md`, corpus golden de 91 casos).
3. **Disciplina ADR**: las decisiones de arquitectura se registran en
   `docs/adr/` antes o junto con el código que las implementa.
4. **Firmware = autoridad física**: el runtime refleja
   `calibration.h`/`pins.h`; no dupliques constantes (test de
   consistencia).
5. **Estilo**: `ruff check .` y `mypy src` limpios.

## Flujo de trabajo

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[cli,serial,dev]"
pytest tests -q          # 169 tests
ruff check .
mypy src
make -C firmware/sirah-eyes/tests/host core_tests
```

Commits en formato Conventional Commits (`feat(runtime):`, `fix(hardware):`,
`docs:`, `test:`...). El gate de CI corre lint, contract y unit.

## Hardware

Sin módulo físico, toda verificación se hace con el twin
`FakeESP32` (`--fake`) y tests; la evidencia física VERIFIED se registra
en `docs/hardware/pin-map.md` con fecha, y gana sobre cualquier
contradicción futura.