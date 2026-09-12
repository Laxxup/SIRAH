# Personalización de SIRAH

Este directorio contiene los archivos de personalidad de SIRAH.
Puedes editarlos para cambiar la identidad, personalidad, estilo de diálogo y saludo de arranque del robot.

## Archivos

| Archivo | Propósito |
|---|---|
| `identity.md` | Quién es SIRAH. |
| `personality.md` | Cómo se comporta y habla. |
| `dialogue-style.md` | Reglas de conversación y límites. |
| `wakeup-style.md` | Instrucciones de estilo para el saludo de arranque. |

## Reglas de seguridad

- **No** inventes biografía, experiencias ni capacidades que el robot no tenga.
- **No** modifiques el formato de salida JSON ni la lista de acciones: esos contratos técnicos están protegidos en el código fuente.
- `actions.md` permanece en `config/` porque describe la interfaz física del robot.

## Cómo funciona

Si un archivo está vacío o no existe, SIRAH usa su valor por defecto interno.
Para restaurar los valores originales, borra los archivos o copia el contenido inicial desde el repositorio.
