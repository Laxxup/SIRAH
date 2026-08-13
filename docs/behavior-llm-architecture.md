# Future Behavior And LLM Boundary

This is a design boundary, not an enabled feature. SIRAH's reactive eye motion,
blink and physical safety remain deterministic and local.

```text
perception -> StateStore -> EventDetector -> BehaviorPolicy
                                         -> optional LLM -> structured intent
                                         -> PolicyValidator -> high-level action
```

The event detector is edge-triggered: person arrival, speech completion and
other semantic changes. The policy applies cooldowns, deduplication and a
single in-flight request. The optional LLM may propose only a closed structured
intent. It never sends text or commands to the ESP32.

The validator rejects unknown intents, state-incompatible proposals, timeouts,
budget exhaustion and cooldown violations. Rejection resolves to silence or a
deterministic clarification, never to a physical fallback command.

Any implementation must first add an ADR, shadow mode, replay scenarios and
metrics for latency, token use, rejected intents and false proactivity.

The shadow coordinator accepts only a semantic event and a derived
`Transcript`. It builds an `IntentRequest`, calls an injected proposer, and
records either the structured proposal or its rejection. It has no runtime,
transport, audio-capture, TTS, or physical-action dependency.
