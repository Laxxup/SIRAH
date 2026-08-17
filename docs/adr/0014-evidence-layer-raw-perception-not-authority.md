# ADR-0014 — Evidence layer: raw perception is never authority

Status: accepted (M2). Applies to: v0.3.x perception architecture.

## Context

YuNet, MediaPipe, future YOLO and object detectors produce noisy,
frame-level outputs. If raw detections directly triggered behavior or
conversation, SIRAH would flicker, over-react and leak model noise into
decisions. Conversation must never stream raw frames or landmark streams.

## Decision

1. Every model output is a `RawObservation` (source, kind, value,
   confidence, observed_at, track_id) normalized at the boundary — no
   vendor types leave the adapter (`src/sirah/perception/evidence.py`).
2. Raw observations land in `EvidenceHub`/`EvidenceFilter`: temporal
   confirmation, hysteresis switching, TTL expiry, release grace and
   one-shot edge events with cooldown. Only then do they become
   `StableState` / `StableEvent` that behavior and conversation may
   consume.
3. `WorldState` carries a `PerceptionFacts` snapshot with `observed_at`
   and per-state temporal validity, so every visual fact exposed to
   conversation has freshness semantics (fresh vs stale).
4. Raw perception MUST NOT directly trigger physical or conversational
   side effects. ML output is observation, not authority. Downstream
   layers (evidence → WorldState → attention/arbitration → behavior,
   and WorldState → conversation) decide.

## Consequences

- Face, gesture and future object sources share one generic mechanism.
- Deterministic, clock-injected, hardware-free unit tests (test_evidence
  + test_world_state) guard the state machines.
- Identity defaults to UNKNOWN; no guessing.
- Facial geometry maps to functional facts (`left_eye_closed`), never to
  psychological/emotional claims without a designed inference layer.
