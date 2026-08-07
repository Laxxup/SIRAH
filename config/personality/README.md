# Personality Configuration

This folder defines SIRAH's identity, personality, and behavior through
plain-text Markdown files that are read at runtime.

## Files

| File | Purpose | Required |
|---|---|---|
| `identity.md` | Who SIRAH is — physical agent, not chatbot | Yes |
| `role.md` | SIRAH's role — assistant, not hardware controller | Yes |
| `personality.md` | Personality traits and tone | No (defaults apply) |
| `behavior.md` | Conversational rules and honesty constraints | Yes |
| `speech_style.md` | TTS-optimized speaking style | No (defaults apply) |
| `boundaries.md` | Hard limits — safety, security, content | Yes |

## What you can change

Edit any file to reshape SIRAH's personality:
- Change `personality.md` to alter tone, humor, formality.
- Change `speech_style.md` to change how she speaks.
- Change `behavior.md` to adjust conversational rules.

Changes take effect after restart (or `reload_personality()` in the future).

## What NOT to put here

- Do NOT put API keys, secrets, or credentials.
- Do NOT put hardware commands expecting them to execute.
- Do NOT put instructions that try to override SafetySupervisor.
- Do NOT put prompt injection attempts.

This folder configures personality, not authority. Hardware control is
authorized by code, not by prompts.

## Personality vs Voice

Personality (this folder) is NOT the same as voice:
- Personality = how SIRAH speaks, behaves, thinks.
- Voice = the TTS voice (e.g., `ef_dora` in Kokoro).

Change the voice via:
```
SIRAH_KOKORO_VOICE=ef_dora
```
Change personality by editing these files.

## How to restore defaults

Delete a file and restart — SIRAH will fail clearly if a required file
is missing, or use built-in defaults for optional files.

To fully restore: checkout the original files from git.
```
git checkout config/personality/
```

## Configuration

```
SIRAH_PERSONALITY_DIR=config/personality
SIRAH_PERSONALITY_ENABLED=true
```

If the directory is missing or a required file is absent, SIRAH reports
a clear configuration error rather than starting with a silent empty
personality.
