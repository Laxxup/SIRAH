# Contributing to SIRAH

SIRAH es un proyecto abierto. Puedes contribuir con código, documentación, personalidad o reportes de problemas.

## Primeros pasos

1. Haz un fork del repositorio.
2. Clona tu fork.
3. Crea una rama para tu cambio: `fix/...`, `docs/...`, `feature/...`.
4. Realiza un cambio enfocado y coherente.
5. Ejecuta los checks correspondientes (ver tabla abajo).
6. Abre un Pull Request contra `main`.

No necesitas cambiar `module github.com/Laxxup/SIRAH` para contribuir mediante Pull Request. Eso solo es necesario si creas un proyecto derivado independiente a largo plazo.

## Checks

| Tipo de cambio | Verificación |
|---|---|
| Go / general | `make check` |
| Vision / OpenCV | `make check-opencv` |
| Firmware | `make check-firmware` |
| Persona / prompts | `make check` |

Ejecuta al menos el target relevante antes de abrir el PR.

## Persona y prompts

Para modificar el carácter de SIRAH utiliza los archivos en `config/persona/`:

- `identity.md` — quién es SIRAH.
- `personality.md` — cómo se comporta y habla.
- `dialogue-style.md` — reglas de conversación y límites.
- `wakeup-style.md` — instrucciones de estilo para el saludo de arranque.

**No** uses estos archivos para modificar:

- acciones físicas;
- formato de respuesta JSON;
- marcadores de gestos;
- restricciones de Timeline o Motion;
- contratos del runtime.

Un PR de personalidad no debería necesitar modificar código Go salvo que estés agregando una capacidad nueva real.

## Firmware, calibración y HIL

Algunos cambios requieren hardware físico para validarse completamente (HIL). Si tu cambio afecta:

- movimiento, límites físicos, servos;
- calibración, mapping, protocolo físico;

indica explícitamente en el PR si realizaste o no pruebas con hardware.

No es obligatorio tener hardware para contribuciones de:

- documentación;
- persona / prompts;
- lógica LLM;
- cambios headless.

### Calibración

La fuente canónica de calibración es `config/eyes-calibration.toml`.
No edites manualmente `firmware/sirah/calibration.h`; ese archivo se genera desde la configuración con:

```sh
python3 scripts/generate_eyes_calibration.py
```

`make check` verifica que el header esté al día.

## Secretos y privacidad

Nunca incluyas en commits:

- `.env` con credenciales reales;
- API keys, tokens o credenciales;
- grabaciones privadas, WAV personales, transcripciones privadas;
- dumps de conversaciones.

`.env.example` es público y no debe contener datos reales.

## Modelos, voces y licencias

- No subas modelos o voces sin conocer su licencia.
- Conserva atribución y licencia de assets externos cuando corresponda.
- Si versionas un modelo grande o binario, documenta su procedencia y preferiblemente su checksum.
- Una voz Piper personalizada no debe añadirse automáticamente al repo.

El código propio de SIRAH usa licencia MIT, pero eso no altera las licencias de dependencias, modelos o assets externos.

## Proveedores LLM

Si cambias o añades compatibilidad con un proveedor LLM, prueba las rutas realmente utilizadas por SIRAH. El runtime actual depende de compatibilidad con la API de OpenAI (streaming opcional). Documenta:

- endpoint esperado;
- esquema de respuesta necesario;
- autenticación si forma parte del contrato actual.

## Commits

No es necesario usar Conventional Commits. Prefiere mensajes cortos y humanos:

- `Fix terminal exit handling`
- `Update Piper setup`
- `Add configurable personality`

Si prefieres usar `feat:`, `fix:`, etc., no está prohibido; simplemente no es requisito.

## Pull Requests

Incluye únicamente:

- qué cambió;
- por qué;
- qué checks ejecutaste;
- si hay validación HIL que no pudiste realizar.

No añadas plantillas extensas, checklist obligatorias, changelog forzado ni issues obligatorios.
