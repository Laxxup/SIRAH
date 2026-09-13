# Personalización de SIRAH

SIRAH usa un formato nativo de personalidad: archivos `.persona.json`. Cada archivo describe completamente una personalidad conversacional.

## Formato nativo

```json
{
  "schema": "sirah_persona",
  "version": 1,
  "display_name": "SIRAH",
  "character_profile": "",
  "personality": "Sueles ser tranquila, directa...",
  "speech": "Hablas en español latino neutral...",
  "behavior": "Cuando no sabes algo, lo reconoces...",
  "examples": [],
  "wakeup_style": "Genera el saludo de arranque...",
  "metadata": {}
}
```

## Campos

| Campo | Descripción |
|---|---|
| `schema` | Siempre `"sirah_persona"`. |
| `version` | Siempre `1`. |
| `display_name` | Nombre conversacional. Vacío = "SIRAH". |
| `character_profile` | Historia/personaje/contexto ficticio. No define capacidades físicas. |
| `personality` | Rasgos de personalidad. |
| `speech` | Estilo de habla (formalidad, muletillas, longitud). |
| `behavior` | Tendencias conversacionales (cómo reaccionar ante bromas, emociones, etc.). |
| `examples` | Ejemplos de diálogo/comportamiento. Máximo 10 elementos. |
| `wakeup_style` | Instrucciones para el saludo de arranque. |
| `metadata` | Información sobre origen (importación, autor, etc.). No afecta runtime. |

## Cómo seleccionar una personalidad

### Por nombre de perfil

```bash
export SIRAH_PERSONA=eva
./sirah
```

SIRAH buscará en este orden:
1. `personas/eva.persona.json`
2. `config/persona/default.persona.json`
3. Personalidad compilada interna (BuiltInPersona)

### Modo simple (principiantes)

```bash
# Sin SIRAH_PERSONA definido
cp mi-perfil.persona.json personas/active.persona.json
./sirah
```

SIRAH buscará:
1. `personas/active.persona.json`
2. `config/persona/default.persona.json`
3. BuiltInPersona

> **Nota:** Character Cards JSON externas (`.json`) todavía no son compatibles directamente. El soporte de carga directa e importación se añadirá en un PR posterior.

## Seguridad

- **No** puedes modificar el formato de salida JSON, la lista de acciones, ni el contrato técnico desde una persona. Estos están protegidos en el código fuente.
- Una persona puede contener ficción ("soy una exploradora de mundos virtuales"), pero eso no crea capacidades físicas reales.
- Campos desconocidos en una `.persona.json` nativa causan error de validación y fallback.

## default.persona.json

Este archivo se genera automáticamente desde `BuiltInPersona()` en el código fuente. No edites manualmente; si cambia el código, regenera con:

```bash
go run scripts/generate-default-persona.go > config/persona/default.persona.json
```

## Volver al default

```bash
unset SIRAH_PERSONA
```

O elimina el perfil activo:

```bash
rm personas/eva.persona.json
```
