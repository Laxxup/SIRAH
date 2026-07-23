# ADR-002: Reconstruction from the legacy prototype

## Estado

Aceptado.

## Contexto

SIRAH cuenta con un
[prototipo experimental anterior](https://gitlab.com/Laxxup/ipt-sirah) que
exploró Gemini, Vosk, Piper, SQLite, cámaras, reconocimiento facial, MQTT,
ESP32-CAM, GTK, LibAdwaita, instalación, empaquetado y manejo de errores.

El prototipo proporcionó experiencia práctica, pero sus componentes evolucionaron
antes de que existieran fronteras estables entre dominio robótico, seguridad,
estado, conversación, percepción, dispositivos y composición. La presencia de
una tecnología en ese repositorio no demuestra por sí sola que esté completa,
probada o disponible en la reconstrucción actual.

El núcleo determinista se desarrolla por separado en
[SIRAH Cortex](https://github.com/Laxxup/SIRAH-Cortex).

## Decisión

Reconstruir SIRAH desde límites arquitectónicos explícitos y evidencia
verificable, sin migrar automáticamente componentes del prototipo.

El prototipo se conserva como referencia histórica. Cada recuperación debe
justificar un consumidor actual, comprobar procedencia y dependencias, ubicarse
en la frontera correcta y validarse primero como experimento. SIRAH puede
depender de Cortex; Cortex nunca depende de SIRAH.

## Consecuencias positivas

- La historia del proyecto y el conocimiento experimental permanecen
  accesibles.
- Las capacidades se incorporan según evidencia y responsabilidad, no por la
  estructura heredada.
- El núcleo determinista permanece separado de proveedores, dispositivos e
  interfaces.
- Los riesgos mecánicos continúan pasando por planificación, seguridad,
  ejecución y `RobotPort`.
- Es posible recuperar ideas valiosas sin restaurar acoplamientos anteriores.

## Consecuencias negativas

- Recuperar una capacidad exige auditoría y validación adicional.
- Parte del código anterior puede necesitar reescritura en lugar de copia.
- La reconstrucción avanza con menos capacidades visibles durante sus primeras
  fases.
- Algunas decisiones de integración permanecen abiertas hasta que exista un
  consumidor comprobable.
