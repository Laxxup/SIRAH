# ADR-004: Primer circuito de iniciativa situada simulada

## Estado

Aceptado para `0.1.0.dev0`, con implementación simulada y parcial.

## Contexto

SIRAH ya podía conversar y ejecutar capacidades explícitas, pero aún no
demostraba percepción, representación situacional ni iniciativa. Cortex ya
ofrece eventos públicos, `Runtime`, `WorldState`, observaciones de presencia y
expiración.

## Decisión

SIRAH publica observaciones simuladas mediante `EventInboxPort` y `Runtime` de
Cortex. El `WorldState` de Cortex sigue siendo la única fuente de presencia,
vigencia y versión de estado.

La memoria de interacción vive en SIRAH porque “ya saludado”, cooldown, modo
silencio, autonomía y TTS son responsabilidades del producto conversacional,
no hechos genéricos del robot.

La iniciativa de saludo comienza con una política determinista. Solo evalúa
presencia vigente, autonomía, silencio, cooldown, TTS, emergencia y actividad
incompatible. Gemini no participa en esa decisión.

TTS usa un puerto pequeño y `FakeSpeechOutput`. No se fuerza dentro de
`RobotPort`, porque hablar no es movimiento mecánico. Piper y proveedores reales
se incorporarán posteriormente mediante el mismo contrato.

Las pruebas y la consola usan adaptadores falsos antes de añadir Vosk, Piper,
audio o hardware real. El router local reconoce únicamente órdenes exactas de
parada antes de consultar inteligencia.

## Alternativas rechazadas

- Duplicar `WorldState` en SIRAH: produciría dos fuentes de verdad.
- Añadir campos de saludo a Cortex: mezclaría producto conversacional con
  estado robótico genérico.
- Usar Gemini para decidir saludos obvios: añadiría latencia y una autoridad
  innecesaria.
- Modelar TTS como `RobotPort`: confundiría audio con control mecánico.
- Crear un servidor o GUI: ampliaría el alcance antes de validar el circuito.

## Consecuencias y revisión

La demostración puede percibir una presencia, actualizar Cortex, saludar una
sola vez, aplicar cooldown, respetar silencio y detener TTS/robot localmente.
La percepción, TTS, identidad de personas y autonomía siguen siendo simulados
o parciales. La decisión deberá revisarse al incorporar STT, TTS real, visión,
identidad persistente o hardware físico.
### Evolución del ciclo social

La presencia simulada se identifica con una clave efímera, no con identidad
humana. `InteractionMemory` es la única fuente de verdad para silencio,
autonomía, TTS y saludos. Los saludos se mantienen pendientes durante la
reproducción y solo se confirman al finalizarla; fallo o cancelación elimina el
pendiente sin marcar a la presencia como saludada. La memoria se poda mediante
reloj inyectado, TTL de 600 segundos y máximo de 128 entradas.

El código se divide por razones de cambio en `interaction.py`, `speech.py`,
`simulation.py`, `local_commands.py` y `situational_runtime.py`; `situational.py`
solo conserva reexports. Piper, Vosk e identidad persistente siguen fuera de
alcance.
