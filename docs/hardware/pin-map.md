# Pin map — SIRAH eyes

**Status: PLACEHOLDER — working map (A5), pending physical verification.**

The initial calibration record (2026-08-08) documents the working map below.
It is NOT definitive evidence: Stage 4 of the implementation plan MUST
verify each actuator physically via sweep. If the sweep contradicts this
map, physical evidence wins and the corrected truth is recorded here.

| Actuator | GPIO (working map) |
|---|---|
| Ojo X | 25 |
| Ojo Y | 26 |
| Párpado superior derecho | 14 |
| Párpado inferior derecho | 27 |
| Párpado inferior izquierdo | 32 |
| Párpado superior izquierdo | 33 |

Source: `sirah-architecture-study/reports/hardware/initial-calibration-2026-08-08.md`.

## Controlled sweep procedure (director — executor: 2026-08-09, env: no serial)

The Stage 4 host gates are green, but this environment has no serial
device (`/dev/ttyUSB*`/`/dev/ttyACM*` absent), so the physical sweep
cannot run here. Execute it on the robot and record evidence below; do
not skip it silently.

Procedure (one actuator at a time, servos unloaded/powered-safe):

1. Flash firmware and connect a terminal at 115200 baud.
2. Expect `READY 1` on boot (protocol.md).
3. For actuator `Ojo X` (pin 25 working): send `TARGET 1 0` ->
   eye must move RIGHT (law: +1 = right); `TARGET -1 0` -> left;
   `TARGET 0 0` -> center ~130°.
4. For `Ojo Y` (pin 26): `TARGET 0 1` -> up (~94°); `TARGET 0 -1` ->
   down (~30°); `TARGET 0 0` -> center (~70°).
5. Eyelid sweep (pins 14/27/32/33): send `BLINK` repeatedly (~1 s
   apart) and confirm: (a) all four eyelids move, (b) sup/inf perceptibly
   converge toward each other (closing), (c) they open fully between
   blinks. A lid that never moves or moves the wrong direction is a
   wrong pin: record the actuator that actually responds on that GPIO.
6. Optional squint spot-check on robot side only, never a wire command
   (squint is calibration data, not protocol).
7. Record one line per GPIO in the table below with date + who +
   behavior observed. If any row contradicts the working map, update
   `platform/pins.h` in the SAME commit as this document and re-run
   Stage 4 gates (host tests + contract) — physical evidence wins (A5).

### Evidence log (to be completed by director on hardware)

| GPIO | Working map | Sweep result (date, who, behavior) | Verdict |
|---|---|---|---|
| 25 | Ojo X | | |
| 26 | Ojo Y | | |
| 14 | Sup der | | |
| 27 | Inf der | | |
| 32 | Inf izq | | |
| 33 | Sup izq | | |