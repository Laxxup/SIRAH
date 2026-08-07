# ADR-003: Frontera de la SIRAH Laboratory Console

## Estado

Reemplazado por el cliente `sirah-console` del runtime headless.

## Contexto

SIRAH necesita una demostración interactiva del agente robótico modular sin
crear todavía una GUI, un servidor web ni un segundo lugar donde vivan las
políticas. El sistema ya dispone de conversación textual, contexto temporal,
catálogo de capacidades, ejecución mediante Cortex y un robot simulado.

## Decisión

La consola consume un socket Unix autenticado del único `SirahRuntime`. Usa
`SIRAH_RUNTIME_SOCKET` y `SIRAH_CLI_SECRET`; no crea el sistema, no construye
adaptadores ni recibe configuración de dispositivos.

La consola puede:

- enviar texto y consultar el snapshot expuesto por el runtime;
- mostrar respuestas y componentes serializados;
- solicitar únicamente capacidades ya autorizadas por el runtime.

La consola no contiene reglas de seguridad, no crea `RobotCommand`, no accede
a Cortex, no llama directamente a `RobotPort`, no selecciona dispositivos y no
persiste datos.

## Consecuencias positivas

- La demostración hace visible la modularidad y la degradación progresiva.
- El runtime mantiene una sola asamblea y una sola autoridad de hardware.
- Un futuro panel puede consumir el mismo socket y snapshots.
- La lógica de dominio permanece fuera de la interfaz.

## Consecuencias negativas

- La consola no es una interfaz de usuario definitiva.
- La representación del presente es resumida y no sustituye telemetría real.
- Los clientes deben recibir y proteger su propio secreto compartido.

## Evolución futura

Un panel local podrá añadirse como consumidor de los servicios existentes. No
deberá mover políticas, estado autoritativo ni ejecución mecánica hacia la
interfaz.
