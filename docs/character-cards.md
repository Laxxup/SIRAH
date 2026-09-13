# Character Cards

SIRAH supports importing **Character Cards** (V1, V2, V3 JSON) as persona profiles. Character Cards are a popular format in the AI roleplay community for describing AI personalities, behaviors, and speech patterns.

## Supported Formats

| Format | Detection | Notes |
|--------|-----------|-------|
| V1 | Top-level `name`, `personality`, `description` fields | Legacy format |
| V2 | `"spec": "chara_card_v2"` with `data` envelope | Most common format |
| V3 | `"spec": "chara_card_v3"` with `data` envelope | Latest format |

## Security Model

Character Cards may contain fields that could override SIRAH's hardware identity or system behavior. The adapter applies a strict security policy:

### Blocked Fields (Security)
These fields are **never** merged into the persona and are reported as blocked:

- `system_prompt`
- `post_history_instructions`

### Ignored Fields
These fields are not mapped to SIRAH's persona model and are reported as ignored:

- `scenario`
- `first_mes`
- `alternate_greetings`
- `lorebook`
- `mes_example` (split into `Examples` instead)

### Protected Identity
The persona is treated as a **conversational overlay only**. It cannot modify:
- Voice settings
- Firmware configuration
- Vision pipeline
- Motion/servo behavior
- STT/TTS/VAD parameters

## Mapping Rules

| Character Card Field | SIRAH Persona Field | Notes |
|---------------------|---------------------|-------|
| `name` | `display_name` | |
| `personality` | `personality` | |
| `description` | `character_profile` | `[Personality]` section extracted if present |
| `mes_example` | `examples` | Split by `<START>` into array |
| `first_mes` | — | Ignored |
| `scenario` | — | Ignored |
| `alternate_greetings` | — | Ignored |
| `creatorcomment` | — | Ignored |
| `tags` | — | Ignored |
| `creator` | — | Ignored |
| `character_version` | — | Ignored |
| `extensions` | — | Ignored |

### `[Personality]` Extraction
If `description` contains a `[Personality]` section (common in V1/V2 cards), that section is extracted and used as the `personality` field. The remaining text goes to `character_profile`.

## Usage

### Inspect a Character Card
```bash
sirah persona inspect card.json
```
Shows the detected format, any blocked/ignored fields, warnings, and the mapped persona.

### Import a Character Card
```bash
sirah persona import card.json --profile eva
```
Converts the card to a native SIRAH persona and writes it to `~/.local/share/sirah/persona/eva.persona.json`.

To overwrite an existing profile:
```bash
sirah persona import card.json --profile eva --force
```

### List Profiles
```bash
sirah persona list
```
Shows all available profiles (both native `.persona.json` and raw `.json` cards).

## Runtime Loading

SIRAH's runtime can load Character Cards directly without importing:

- **Active mode** (`SIRAH_PERSONA=`):
  1. `active.persona.json` (native)
  2. `active.json` (Character Card)
  3. `default.persona.json`
  4. Built-in persona

- **Named mode** (`SIRAH_PERSONA=eva`):
  1. `eva.persona.json` (native)
  2. `eva.json` (Character Card)
  3. `default.persona.json`
  4. Built-in persona

Native profiles always take priority over raw Character Cards.

## Limits

The adapter enforces the same limits as native personas:

- `display_name`: 64 runes max
- `character_profile`: 8192 runes max
- `personality`: 4096 runes max
- `speech`: 2048 runes max
- `behavior`: 2048 runes max
- `examples`: 32 items max, 1024 runes each
- `wakeup_style`: 256 runes max

Warnings are generated (not silent truncation) when limits are exceeded.

## File Locations

- **Profiles**: `~/.local/share/sirah/persona/` (or `$XDG_DATA_HOME/sirah/persona/`)
- **Default persona**: `~/.config/sirah/default.persona.json`

## Empty Fields

Empty Character Card fields are **not** merged with the built-in persona. The selected persona is used as a complete unit.
