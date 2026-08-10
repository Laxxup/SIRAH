# SIRAH v0.3.0

## Sistema Inteligente Robótico de Asistencia Humana

SIRAH es un **proyecto universitario del Instituto Tecnológico de Ciudad Madero (ITCM)**, desarrollado dentro del **Taller de Robótica**, con colaboración del **IPT de Tampico Centro**.

El objetivo del proyecto es desarrollar un **robot humanoide educativo**, integrando robótica, electrónica, programación, control y sistemas embebidos.

Actualmente, SIRAH se encuentra en etapa de **prototipo en desarrollo**.

---

## Current status

SIRAH se desarrolla progresivamente mediante diferentes subsistemas.

Actualmente se encuentran implementados o en desarrollo:

* Runtime en Python con `asyncio`.
* Comunicación PC ↔ ESP32 mediante protocolo v1.0.
* Firmware ESP32.
* Control de servomotores mediante PCA9685.
* Sistema de ojos con movimiento 2D.
* Parpadeo, easing, límites y pose segura.
* Calibración de actuadores.
* `FakeESP32` para pruebas sin hardware.
* Pruebas unitarias, contract tests e integración offline.
* Infraestructura inicial de percepción y comportamiento.

En desarrollo:

* Percepción mediante webcam.
* Seguimiento visual.
* Integración de los diferentes subsistemas del robot.
* Nuevas capacidades de interacción.
* Futuros subsistemas humanoides.

---

## Eye subsystem

El sistema de ojos es uno de los primeros subsistemas funcionales de SIRAH.

Utiliza un **ESP32**, un **PCA9685** y seis servomotores:

* Eye X.
* Eye Y.
* Cuatro párpados.

El firmware mantiene la responsabilidad sobre el control físico de los actuadores, incluyendo parpadeo, easing, límites, watchdog y pose segura.

El runtime en PC/Raspberry Pi se comunica con el ESP32 mediante un protocolo definido y también puede ejecutarse utilizando `FakeESP32`, permitiendo realizar pruebas sin hardware.

La documentación específica del subsistema se encuentra en [`docs/hardware/`](docs/hardware/) y [`docs/components/protocol.md`](docs/components/protocol.md).

---

## Getting started

### Sin hardware

El proyecto puede ejecutarse utilizando `FakeESP32`:

```bash
pip install -e ".[cli,serial]"
sirah-runtime --fake --eyes
```

Esto permite probar el runtime sin conectar un ESP32.

### Con hardware

Con el ESP32, PCA9685 y los seis servomotores configurados:

```bash
sirah-runtime --eyes
```

Consulta [`docs/hardware/`](docs/hardware/) antes de utilizar el hardware físico.

---

## Project structure

```text
SIRAH
├── src/              Runtime y software principal
├── firmware/         Firmware ESP32
├── config/           Configuración del sistema
├── tests/             Pruebas automatizadas
├── docs/              Documentación técnica
├── laboratory/        Componentes experimentales
└── scripts/           Herramientas auxiliares
```

La estructura y las responsabilidades de cada componente están documentadas en [`docs/architecture.md`](docs/architecture.md).

---

## Testing

Las pruebas de Python pueden ejecutarse mediante:

```bash
pytest tests -q
```

Las pruebas del firmware:

```bash
make -C firmware/sirah-eyes/tests/host core_tests
```

El contrato del protocolo:

```bash
make -C firmware/sirah-eyes/tests/host contract_checker
```

El proyecto utiliza pruebas unitarias, contratos de protocolo e integración offline para validar sus componentes.

---

## Documentation

La documentación técnica del proyecto se encuentra en [`docs/`](docs/).

* [`architecture.md`](docs/architecture.md) — arquitectura general.
* [`quickstart.md`](docs/quickstart.md) — instalación y primeros pasos.
* [`roadmap.md`](docs/roadmap.md) — etapas de desarrollo.
* [`components/protocol.md`](docs/components/protocol.md) — protocolo PC ↔ ESP32.
* [`hardware/`](docs/hardware/) — hardware, conexiones y calibración.
* [`adr/`](docs/adr/) — decisiones de arquitectura.
* [`CHANGELOG.md`](CHANGELOG.md) — historial de cambios.
* [`CONTRIBUTING.md`](CONTRIBUTING.md) — guía para contribuir.

---

## Development

Para conocer las decisiones técnicas y el estado de las diferentes etapas, consulta el [roadmap](docs/roadmap.md) y los [ADR](docs/adr/).

---

## License

SIRAH está disponible bajo la **Apache License 2.0**.

Consulta [`LICENSE`](LICENSE) para los términos completos de la licencia.

