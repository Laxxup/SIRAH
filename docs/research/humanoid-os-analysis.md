# Research: HumanoidOS

**Repositorio:** [ashishjsharda/humanoid-os](https://github.com/ashishjsharda/humanoid-os)
**Fecha de análisis:** 2026-08-05
**Relevancia para SIRAH:** MEDIA (fase 4 — cuerpo bípedo)

## Resumen

HumanoidOS es un sistema operativo open-source para robots humanoides bípedos.
Ofrece control en tiempo real (1kHz), balance ZMP, 7 tipos de marcha, recuperación
de empuje, cinemática inversa, navegación con visión y simulación PyBullet.

## Lecciones clave

### 1. Arquitectura en capas

```
core/          → Control loop 1kHz, state management
locomotion/    → Balance ZMP, gaits, push recovery
kinematics/    → IK Jacobian 7-DOF, DH parameters
navigation/    → A* path planner, pure-pursuit controller
sensors/       → Depth raycasting, occupancy grid
hal/           → Hardware Abstraction Layer (sim + real serial/CAN)
ros2/          → ROS 2 bridge (joint states, IMU, odom, cmd_vel)
simulation/    → PyBullet integration
```

**Aplicación en SIRAH:** Esta arquitectura en capas es exactamente lo que SIRAH ya tiene
(`core/`, `intelligence/`, `perception/`, `voice/`, `action/`). Para la fase 4 (cuerpo),
SIRAH podría agregar capas `locomotion/` y `kinematics/` siguiendo este modelo.

### 2. Hardware Abstraction Layer

HumanoidOS tiene una capa HAL que abstrae si el robot es real o simulado:

```python
from hal.simulation_hal import SimulationHAL
hal = SimulationHAL(robot)    # PyBullet
hal.initialize()
states = hal.read_joint_states()
```

**Aplicación en SIRAH:** Ya tenemos `SimulatedRobot` y `SimulatedPerception`. 
Para el cuerpo físico, implementar `PhysicalRobotHAL` que traduzca comandos 
a Serial/CAN hacia los ESP32.

### 3. ROS 2 bridge con stubs

El puente ROS 2 de HumanoidOS funciona incluso sin ROS 2 instalado (stubs).
Esto permite desarrollo y testing sin depender del ecosistema ROS completo.

**Aplicación en SIRAH:** `bridge/` ya sigue este patrón. `serial_esp32.py` y `mqtt.py`
son stubs que funcionan sin hardware.

### 4. Performance

- Control loop: 1000 Hz
- IK solver: <5ms por solve (7-DOF)
- 81 tests automatizados
- Velocidad de marcha: 0.1-1.5 m/s

**Aplicación en SIRAH:** Referencia de performance para fase cuerpo.

## Lo que SIRAH no necesita (por ahora)

- ZMP balance (no tenemos piernas aún)
- Gait generation (no caminamos)
- PyBullet simulation (usamos fakes deterministas)
- Navigation stack (somos estacionarios)

## Lo que SIRAH adoptará en fase 4

1. **HAL pattern** — abstraer servo/motor control
2. **Kinematics IK** — para brazos 6DOF con ESP32
3. **ROS 2 bridge con stubs** — ya tenemos el patrón
4. **Test coverage** — 81 tests es buen benchmark
