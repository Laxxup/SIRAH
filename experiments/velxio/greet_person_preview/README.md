# Velxio greeting preview

- Estado: Experimental
- Validación: Validado en simulación
- Origen: copia del repositorio SIRAH Cortex, commit `ea10d96`

## Propósito y alcance

Demostrar de forma reproducible un saludo moviendo un único servo simulado. No
es el controlador facial, no representa siete servos y no define el protocolo
final de SIRAH.

## Entradas y salidas

Recibe líneas Serial del protocolo explícitamente experimental
`experimental-serial-v0`. Emite `READY`, `PROTOCOL`, `LIMITS`, `ACCEPTED`,
`APPLIED` o `REJECTED` para diagnóstico de la demostración.

## Interfaces, hardware y software

El sketch usa ESP32, `ESP32Servo` y un servo conectado al pin descrito por el
diagrama Velxio/Wokwi exportado. `greet_person_preview.ino` es la fuente legible;
`velxio_export/` y el ZIP preservan el artefacto importable de simulación.

## Dependencias y seguridad

Requiere el entorno de simulación y la biblioteca de servo. Los límites del
sketch pertenecen a la demo; no son calibraciones del robot real. No debe
cargarse en hardware sin revisar alimentación, pinout y límites mecánicos.

## Prueba

1. Importar `greet_person_preview.zip` o los archivos de `velxio_export/`.
2. Iniciar la simulación y confirmar los mensajes `READY` y `PROTOCOL`.
3. Reproducir las líneas de `example_serial_session.txt`.
4. Confirmar rechazo de entradas fuera de límites y el orden de respuestas.

## Resultado y decisión

El artefacto fue conservado como evidencia de simulación. No se promueve a
`firmware/` ni a un adaptador estable. El siguiente paso es decidir si aún
aporta evidencia al controlador real; en caso contrario puede deprecarse sin
convertir su protocolo en contrato público.
