# ADR-003: Frontera de la SIRAH Laboratory Console

## Estado

Aceptado para la pre-alpha `0.1.0.dev0`.

## Contexto

SIRAH necesita una demostración interactiva del agente robótico modular sin
crear todavía una GUI, un servidor web ni un segundo lugar donde vivan las
políticas. El sistema ya dispone de conversación textual, contexto temporal,
catálogo de capacidades, ejecución mediante Cortex y un robot simulado.

## Decisión

Crear `examples/interactive_conversation.py` como SIRAH Laboratory Console.
La consola usa argparse, conserva una sesión en memoria y consume
`ConversationOrchestrator`, `ComponentRegistry` y `SystemSnapshot`.

La consola puede:

- mostrar respuestas, decisiones, autorizaciones, comandos y eventos resumidos;
- mostrar componentes disponibles, simulados y no configurados;
- ejecutar únicamente capacidades que ya atraviesan la política y Cortex;
- ofrecer comandos locales de diagnóstico y limpieza de sesión.

La consola no contiene reglas de seguridad, no crea `RobotCommand`, no accede
al SDK de Gemini, no llama directamente a `RobotPort` y no persiste datos.

## Consecuencias positivas

- La demostración hace visible la modularidad y la degradación progresiva.
- El fake permite trabajar sin red y Gemini sigue siendo intercambiable.
- Un futuro panel puede consumir los mismos servicios y snapshots.
- La lógica de dominio permanece fuera de la interfaz.

## Consecuencias negativas

- La consola no es una interfaz de usuario definitiva.
- El estado desaparece al cerrar el proceso.
- La representación del presente es resumida y no sustituye telemetría real.
- Un panel futuro requerirá contratos de transporte y autenticación propios.

## Evolución futura

Un panel local podrá añadirse como consumidor de los servicios existentes. No
deberá mover políticas, estado autoritativo ni ejecución mecánica hacia la
interfaz.
