# Behavior LLM Design Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a safe future architecture for event-driven behavior and LLM proposals without adding runtime dependencies or physical authority.

**Architecture:** Local perception updates a semantic state store. Edge-triggered events enter a deterministic policy with cooldown and single-flight control. An optional LLM produces a structured intent that code validates before it can request existing high-level eye behavior.

**Tech Stack:** Markdown, future Pydantic and Ollama integration only.

## Global Constraints

- Refer to the project only as `SIRAH`; do not expand its name.
- Do not add Ollama, STT, TTS, Pydantic or network dependencies in this work.
- No text or command from an LLM reaches the ESP32 directly.

---

### Task 1: Record the future behavioral boundary

**Files:**
- Create: `docs/behavior-llm-architecture.md`
- Modify: `docs/roadmap.md`
- Modify: `docs/adr/README.md`

- [ ] **Step 1: Define data flow and ownership**

Document this exact boundary:

```text
perception -> StateStore -> EventDetector -> BehaviorPolicy
                                         -> optional LLM -> SirahIntent
                                         -> PolicyValidator -> high-level action
```

Specify that reactive gaze, blink and safety stay deterministic and that the
only LLM output is a small closed intent schema.

- [ ] **Step 2: Define rejection and degradation rules**

Document: unknown intent, invalid state transition, network timeout, exhausted
budget and cooldown all resolve to `silent` or a deterministic clarification;
none produces a physical fallback command.

- [ ] **Step 3: Add roadmap exit criteria**

Add a future milestone requiring shadow mode, replay scenarios, latency/token
metrics, false-proactivity measurement and an ADR before any implementation.

- [ ] **Step 4: Review consistency**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS; documentation changes add no dependency.

- [ ] **Step 5: Commit**

```bash
git add docs/behavior-llm-architecture.md docs/roadmap.md docs/adr/README.md
```
