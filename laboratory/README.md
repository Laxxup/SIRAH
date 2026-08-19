# SIRAH Intelligence Laboratory

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana** (in Spanish,
never translated). This laboratory is the experimental-intelligence
counterpart of the stable eyes subsystem in this repository.

**Status: SCAFFOLD — OFF by default (ADR-0007).**

This directory will host experimental intelligence work (LLM providers,
prompts, context, memory, reasoning, decision policies, tools,
conversational behavior, latency, evaluations) AFTER the stable physical
runtime exists.

Rules (ADR-0007):

- OFF by default: nothing here may be imported, started or wired by the
  stable runtime, and vice versa.
- Experiments run in simulation or shadow mode with NO unrestricted
  authority over physical servos; proposals are reviewed and gated.
- No "SIRAH Cortex" component exists or will be created under this name.

As of the publication pass, the directory contains `README.md`, `INTERFACE.md`
and reusable latency diagnostics (`latency_aggregate.py`, its sample output
`sample_lab_output.log`, and the Edge TTS first-audio probe). Nothing here is
imported, started or wired by the stable runtime; experiments run only after
the stable physical runtime exists.