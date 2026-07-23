# Historia de SIRAH

SIRAH no comienza con el repositorio actual. La estructura presente es una
reconstrucción arquitectónica que conserva la experiencia del proyecto y
redefine qué evidencia se necesita antes de declarar una capacidad como
implementada.

## Prototipo experimental

El [prototipo anterior](https://gitlab.com/Laxxup/ipt-sirah) exploró una visión
amplia del sistema. Incluyó trabajo relacionado con:

- Gemini;
- reconocimiento de voz con Vosk;
- síntesis de voz con Piper;
- memoria respaldada por SQLite;
- cámaras y reconocimiento facial;
- comunicación MQTT y ESP32-CAM;
- GUI con GTK y LibAdwaita;
- instalación, empaquetado y manejo de errores.

Esta lista describe áreas exploradas. No afirma que todas alcanzaran el mismo
nivel de integración, prueba, estabilidad o disponibilidad, ni que formen parte
del repositorio actual.

El prototipo permitió obtener experiencia real con proveedores, dependencias,
dispositivos e interfaces. También produjo conocimiento sobre el costo de
integrar muchas capacidades antes de estabilizar el dominio robótico, la
seguridad, el estado y los contratos entre componentes.

## Problemas descubiertos

La experiencia del prototipo mostró la necesidad de:

- separar decisiones robóticas deterministas de proveedores y dispositivos;
- impedir que un LLM tenga autoridad mecánica directa;
- distinguir estado presente, memoria conversacional y persistencia histórica;
- validar comandos antes de alcanzar firmware o hardware;
- reducir el acoplamiento entre conversación, percepción, GUI y ejecución;
- respaldar cada capacidad con pruebas y evidencia reproducible;
- diferenciar prototipos, experimentos y componentes estables.

Estos hallazgos motivan la reconstrucción; no invalidan el valor experimental
del trabajo anterior.

## Separación de SIRAH Cortex

El núcleo determinista se separó en
[SIRAH Cortex](https://github.com/Laxxup/SIRAH-Cortex). Cortex posee dominio,
eventos, `WorldState`, Runtime, planificación, seguridad, ejecución, tracking,
cancelación, emergencia y contratos abstractos esenciales.

SIRAH es el sistema completo y puede depender de Cortex. Cortex no depende de
SIRAH. Percepción, conversación, proveedores, dispositivos, adaptadores
concretos, firmware y composición permanecen del lado de SIRAH.

La distribución alpha local `sirah-cortex` `0.1.0a1` constituye un hito de la
reconstrucción, no una certificación de hardware ni una API estable definitiva.

## Reconstrucción actual

El repositorio actual comienza de forma mínima a propósito. Conserva
documentación, límites arquitectónicos y experimentos con procedencia
comprobada. No replica la estructura del prototipo ni crea paquetes vacíos para
representar capacidades futuras.

Cada nueva fase debe partir de un caso de uso medible, funcionar sin hardware
cuando sea razonable y declarar su validación. Una capacidad planeada no se
presenta como implementada.

## Recuperación de conocimiento heredado

El código heredado se trata como referencia histórica, no como fuente
autoritativa. Para recuperar una idea o componente:

1. Identificar su propósito y el caso de uso que resolvía.
2. Comprobar procedencia, licencia y dependencias.
3. Revisar pruebas, configuración y evidencia de ejecución disponible.
4. Clasificar su responsabilidad según los límites actuales de SIRAH, Cortex y
   firmware.
5. Aislarlo primero como experimento reproducible.
6. Sustituir supuestos obsoletos sin copiar acoplamientos innecesarios.
7. Confirmar que cualquier acción mecánica atraviese planificación, seguridad,
   ejecución y `RobotPort`.
8. Promoverlo únicamente después de obtener evidencia de simulación o hardware.

No se migra automáticamente un módulo por compartir nombre con una capacidad
planeada. Tampoco se descarta conocimiento útil solo porque su implementación
pertenezca a una arquitectura anterior.
