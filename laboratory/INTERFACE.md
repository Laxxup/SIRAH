# Laboratory ↔ stable runtime interface (provisional)

Status: PROVISIONAL — nothing is wired at Stage 1. This file only
documents the intended boundary so the scaffold is explicit (ADR-0007).

- The laboratory interacts with the stable runtime through **proposal
  gates**: experiments propose an interface; the director approves it
  before any wiring.
- The laboratory must run in **simulation or shadow mode**; it never
  issues servo commands directly and never bypasses firmware limits.
- The stable runtime treats the laboratory as ABSENT: no imports, no
  plugins, no hooks in the product code.