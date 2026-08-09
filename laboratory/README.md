# SIRAH Intelligence Laboratory

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

At Stage 1 this is an empty scaffold: `README.md` + `INTERFACE.md` only.