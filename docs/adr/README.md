# ADRs — index

Architecture Decision Records for SIRAH v0.3.0 (subsistema de ojos de
SIRAH — **Sistema Inteligente Robótico de Asistencia Humana**). Accepted
by the director; all status "applies to v0.3.0". This index is the
repository's own record of the decisions that govern it.

| ID | Title |
|---|---|
| ADR-0001 | ROS 2-agnostic core with optional integration |
| ADR-0002 | Serial as the first PC↔ESP32 transport |
| ADR-0003 | One wire protocol for PC↔ESP32 |
| ADR-0004 | Firmware-owned behaviors (blink, limits, safe poses) |
| ADR-0005 | Synchronicity and damping of X and Y eye axes |
| ADR-0006 | Python version floor and policy |
| ADR-0007 | Intelligence Laboratory separated from stable runtime |
| ADR-0008 | Monorepo layout and repository boundaries |
| ADR-0009 | Calibration lives in config; no serial access for tools |
| ADR-0010 | Testing strategy: fake, replay and HIL gates |
| ADR-0011 | PCA9685 + external 5 V power for the servo rail (accepted 2026-08-09) |
| ADR-0012 | Attention, arbitration and world state as opt-in deterministic layers over the perception→behavior chain (accepted 2026-08-16) |
| ADR-0013 | Telepresence and single camera ownership: one camera owner, fan-out, freshness (proposed, research track) |
| ADR-0014 | Evidence layer: raw perception is never authority; only stable state/events reach behavior and conversation (accepted, M2) |