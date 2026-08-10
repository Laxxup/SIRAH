# Wire protocol PC ↔ ESP32 — SIRAH eyes v1.0

**Status: NORMATIVE** (draft approved scope of Stage 2; ratification pending
director approval — the parser gates will not be implemented before this
spec is approved).

SIRAH = **Sistema Inteligente Robótico de Asistencia Humana**; this
specification governs the eyes subsystem of the general SIRAH project.

- Spec version: **1.0**
- Date: 2026-08-08
- Governs: the PC↔ESP32 channel of the SIRAH v0.3.0 Milestone 1 runtime
  (subsistema de ojos).
- Basis: ADR-0003 (one wire protocol), refined by decisions A1–A4
  (coordinates, heartbeat/watchdog, STATE semantics, no CALIB verb).
- Transport-agnostic grammar: the framing below is defined abstractly;
  §3 defines the only binding implemented in Milestone 1 (serial).

## 1. Overview and scope

The channel carries **commands** (PC→ESP32) and **responses** (ESP32→PC)
as single ASCII lines. Purposes:

1. Stream a normalized gaze setpoint at runtime cadence.
2. Trigger one punctual blink, ask for state, keep the link alive.
3. Report accepted/rejected commands and the firmware's commanded pose.

The channel is **clean**: no timestamps, no debug, no telemetry traces,
no human-readable chatter. Messages are exactly what this spec defines.
Anything else is an error (closed grammar).

In scope: grammar, semantics, error behavior, watchdog, examples.
Out of scope: perception, behavior logic on the PC, calibration values
(firmware authority), blink sequencing (firmware authority, ADR-0004).

## 2. Conformance

- Normative words: MUST, MUST NOT, MAY, SHOULD (RFC 2119 sense).
- PC side (runtime, tools, FakeESP32, tests) MUST implement this spec as
  normative for v0.3.0.
- ESP32 firmware MUST implement this spec as normative for v0.3.0.
- No extension of the grammar is permitted in v0.3.0 (**closed grammar**):
  an unknown verb is a protocol error (ERR 1), never a future hook.
- A parser is conforming if and only if it accepts exactly the language
  defined in §4–§8, including every example in §13, and matches the error
  assignment rules of §9.

## 3. Transport binding (Milestone 1)

- Physical: USB-UART (serial) between the development computer and the
  ESP32. 115200 baud, 8 data bits, no parity, 1 stop bit (8N1). No
  hardware flow control.
- One line = unterminated payload + `\n`. The serial adapter MUST NOT add
  or strip `\r`, timestamps, or prefixes.
- Device path and discovery are runtime configuration (later stages),
  never grammar.
- Future transports (ROS 2, TCP, WebSocket...) MAY carry the same
  grammar unchanged (ADR-0001/0002); framing rules (§4) remain binding.

## 4. Framing and encoding

- Encoding: ASCII, printable subset 0x20–0x7E only, plus the line
  terminator `\n` (0x0A). `\r` (0x0D), tabs (0x09) and other control
  bytes MUST NOT appear and make a line non-conforming.
- Terminator: exactly one `\n` per message. No other terminator exists.
- Maximum line length: **64 bytes including the `\n`**. A line that
  exceeds this limit is invalid (see §9.4).
- Tokens are separated by exactly one space (0x20); leading and trailing
  spaces are not allowed. Multiple consecutive spaces make the line
  invalid.
- Verbs are UPPERCASE and case-sensitive (`target` ≠ `TARGET`).
- No empty-argument singletons: a verb with zero arguments carries no
  trailing space and no "()", no separators.
- Every message is parsed line-by-line in arrival order (FIFO); the
  firmware processes one line and emits at most one response per
  command line.

## 5. Numbers, ranges and units

- The only numeric type on the wire is the **normalized coordinate**:
  dimensionless, range **[−1.000, +1.000]** inclusive.
- Decimal syntax (must match exactly; see ABNF in §6.1):

```
num        = "-" ? ( "0" / nonzero *digit ) [ "." 1*3digit ]
nonzero    = %x31-39     ; 1..9
digit      = %x30-39     ; 0..9
```

  Accepted: `0`, `0.0`, `0.000`, `-0.5`, `1`, `1.000`, `-1`, `0.333`.
  Rejected (ERR 2, malformed): `+1`, `00.5`, `1.`, `.5`, `1.0000`,
  `1e0`, `0,5`, `--1`, `-`.
- Coordinates use the A1 conventions, behavior-independent:

  - x = −1 left, 0 center, +1 right.
  - y = −1 down, 0 center, +1 up.

  Physical servo inversion (`direction`), offsets and mapping to degrees
  are calibration/config concerns and MUST NOT appear on the wire or in
  any behavior code (A1).
- Degrees, microseconds, voltages and other physical units NEVER appear
  on the wire in v0.3.0.

## 6. Command grammar (PC → ESP32)

### 6.1 Grammar

```
command    = target-cmd / center-cmd / blink-cmd / heartbeat-cmd / status-cmd
target-cmd = "TARGET" SP num SP num NL
center-cmd = "CENTER" NL
blink-cmd  = "BLINK" NL
heartbeat  = "HEARTBEAT" NL
status-cmd = "STATUS" NL
NF         = %x0A          ; "\n"
SP         = %x20          ; single space
```

### 6.2 Command table

| Verb | Arguments | Meaning | Response |
|---|---|---|---|
| `TARGET <x> <y>` | 2 required numeric args | Set the gaze reference to (x, y); normalized, A1 signs. Firmware maps to degrees via its calibration and eases toward the target. | `OK` |
| `CENTER` | none | Drive the gaze smoothly to (0, 0) using the firmware recenter policy (eased, not a jump). | `OK` |
| `BLINK` | none | Trigger exactly one punctual blink, merged into the firmware blink FSM (ADR-0004). It is a trigger: it never carries a position sequence. | `OK` |
| `HEARTBEAT` | none | Keep-alive: proves the PC link is alive. | none (see §10.1) |
| `STATUS` | none | Ask the firmware for its current state. | `STATE x y b` |

Numbers MUST be formatted per §5; anything else is an error (§9).

## 7. Response grammar (ESP32 → PC)

### 7.1 Grammar

```
response   = ready-msg / ok-msg / state-msg / err-msg
ready-msg  = "READY" SP "1" NL
ok-msg     = "OK" NL
state-msg  = "STATE" SP num SP num SP blink NL
err-msg    = "ERR" SP errcode NL
blink      = "0" / "1"
errcode    = "1" / "2" / "3" / "5"
```

### 7.2 Response table — cause → response

| Message | Emitted when | Payload |
|---|---|---|
| `READY 1` | ① On firmware boot, once the channel is ready; ② once, after watchdog recovery (§10.4). No other unsolicited messages exist. | protocol version 1 |
| `OK` | After a valid `TARGET`, `CENTER` or `BLINK`. | none |
| `STATE x y b` | After a valid `STATUS`. | last commanded normalized pose (x, y) + blink-in-progress flag b |
| `ERR <code>` | After any invalid line (§9). | error code |

The response order follows command order (FIFO). `HEARTBEAT` produces no
response by design. There is exactly one response per command line
(except `HEARTBEAT`, which has none).

`READY 1` is the only valid content on the wire that the PC did not
request; the PC MUST be able to receive it at any time.

## 8. STATE semantics

- `STATE x y b` reports the value the firmware is **currently commanding**
  (its servo reference), not a measured position: the servos have no
  position feedback (A3). This limitation is normative: downstream
  consumers MUST NOT treat (x, y) as a physical measurement.
- Format: x,y per §5 with exactly 3 decimals (`0.000`, `-0.500`); b is
  `1` while the blink FSM is in CLOSING/CLOSED/OPENING, else `0`.
- During an active eased motion (target change, recenter), x,y reflect
  the instantaneous reference; when idle they equal the last commanded
  target.
- After recenter, x,y converge to `0.000 0.000`.
- The firmware SHALL emit the requested state even mid-blinking.

## 9. Error handling

### 9.1 Error codes

| Code | Meaning | Typical cause |
|---|---|---|
| 1 | Unknown verb | Token not in {TARGET, CENTER, BLINK, HEARTBEAT, STATUS} (including lowercase). |
| 2 | Malformed line | Wrong arity, bad number syntax, double space, extra tokens, `\r`, tab, length > 64 B, non-ASCII. |
| 3 | Out of range | Well-formed number outside [−1,1]. |
| 4 | Reserved | Defined for future protocol versions; never emitted in v1.0. |
| 5 | Internal error | Firmware rejected the command for an internal reason (shall not occur in normal operation). |

### 9.2 Evaluation order (deterministic rejection)

For every line, the firmware MUST apply the checks in this order and
report the FIRST failing code:

1. Length ≤ 64 B including `\n` → else **ERR 2** (and drain, §9.4).
2. Printable ASCII per §4 → else **ERR 2**.
3. Token binding: verb recognized, case-sensitive → else **ERR 1**.
4. Arity exactly as in §6.2 (2 for TARGET, 0 otherwise) → else **ERR 2**
5. Each argument parses as `num`-syntax, left to right → else **ERR 2**.
6. Each parsed value within [−1,1] → else **ERR 3**.

### 9.3 Unknown verbs and malformed lines

- Unknown verb: `ERR 1` and the remainder of the line is ignored.
- Malformed: `ERR 2` and the remainder of the line is ignored.
- A rejected line changes NO machine state: no target, no recenter, no
  blink, no watchdog reset (see §10.3).
- ERR responses are not retried by the firmware; retry policies belong
  to the PC end.

### 9.4 Over-length lines

- If a line exceeds 64 B: the firmware drains up to and including the
  next `\n` (no partial parsing), emits `ERR 2` once, and continues with
  the next line.

### 9.5 Empty lines

- A line consisting only of `\n` (empty payload) is silently ignored:
  no response, no state change. This keeps line-splitting artifacts
  (e.g., host-side `\n` splits) from flooding ERR messages.

### 9.6 Error volume

- The firmware MUST NOT be blocked by invalid traffic: invalid lines
  cost one ERR and no state; floods are rate-limited by the transport
  buffer. A conforming PC MUST NOT deliberately send invalid lines.

## 10. Heartbeat and watchdog

### 10.1 Heartbeat definition

- The PC sends `HEARTBEAT` every **1 s** (±20%) while it intends the
  eyes to track (i.e., always while the runtime is up and eyes armed).
- `HEARTBEAT` is a command; it resets the watchdog; it produces **no
  response** (bandwidth discipline). A conforming firmware MUST NOT reply
  to it.

### 10.2 Timeout

- Watchdog timeout: **3 s** without any valid activity.
- "Activity" = any VALID command line (TARGET, CENTER, BLINK,
  HEARTBEAT, STATUS). An invalid line does NOT reset the watchdog (§9.3).

### 10.3 On timeout (link loss)

- The firmware enters the **safe pose policy**: it eases X/Y to (0, 0)
  (recenter, smooth — not a jump) and stays there for as long as the
  link stays down.
- Autonomous blinking **continues** (ADR-0004): blinking is
  firmware-owned and independent of the link.
- STATE keeps reporting the commanded reference (converging to 0,0).
- The firmware does NOT restart, does NOT re-flash, does NOT close
  eyelids (no additional "sleep" behavior in v1.0).

### 10.4 On recovery

- As soon as a VALID line arrives after a timeout: the watchdog resets,
  the firmware emits `READY 1` exactly once, and the link returns to
  normal operation. The commanded reference remains (0,0) until the PC
  sends a new `TARGET`/`CENTER` (the PC re-synchronizes with `STATUS`
  if it needs to know the pose).
- Recovery does not require a restart on either side.

### 10.5 Precedence

- In normal operation the last valid command wins: `TARGET` supersedes a
  recenter in progress; `CENTER` supersedes the previous target; a
  valid line arriving during the forced recenter stops the recenter and
  resumes tracking per its content.

## 11. Idempotency and repetition

| Situation | Behavior |
|---|---|
| `TARGET` repeated with identical values | `OK` each time; the pose does not change (firmware MAY skip servo writes when the reference is unchanged, but MUST still respond `OK`). |
| `CENTER` while already centered or recentering | `OK` each time; recenter continues (no restart of the easing unless already finished). |
| `BLINK` while the blink FSM is mid-blink (CLOSING/CLOSED/OPENING) | `OK` accepted, blink **discarded** (no double-close, no queued blink). Repetition of `BLINK` therefore does not stack blinks. |
| `BLINK` while idle | Exactly one blink is triggered. |
| `STATUS` at any moment | Always answers `STATE` with the current commanded values. |
| `HEARTBEAT` flood | Accepted silently (no response, watchdog kept alive). |

## 12. What the runtime may send — and what it never controls

**The runtime (PC side) MAY send:** only the five catalog verbs —
`TARGET`, `CENTER`, `BLINK`, `HEARTBEAT`, `STATUS` — exactly per §6.

**The runtime MUST NEVER:**

- issue any other verb (the grammar is closed; nothing else is a
  command, and no future "hidden" verb exists);
- send a CALIB-style command: calibration is configuration-data and
  firmware authority (A4, ADR-0009); no calibration verb exists or is
  planned for v0.3.0 (a future remote-calibration protocol, if any, is a
  separate spec);
- send positions in degrees/µs — the wire is normalized only;
- address an individual servo, eyelid or mechanism — the firmware owns
  all servo composition;
- transmit blink sequences or eyelid trajectories (blink is
  firmware-owned; `BLINK` is only a trigger, A10);
- reboot/reset the firmware (there is no reset verb);
- read physical measurements (there is no feedback channel).

**The firmware (ESP32 side) MUST NEVER:** emit anything other than
`READY 1` (boot/recovery), `OK`, `STATE`, `ERR`; it never streams, never
echoes input, never logs to the wire.

## 13. Examples (normative test cases)

Legend: `→` = expected response (empty = none).

Valid commands:

```text
TARGET 0.0 0.0        → OK
TARGET 0 0            → OK
TARGET 1.000 1.000    → OK
TARGET -1 -0.5        → OK
TARGET 0.333 0.667    → OK
TARGET -1.000 1.000   → OK
CENTER                → OK
BLINK                 → OK
HEARTBEAT             →
STATUS                → STATE -0.333 0.000 0   (example; values depend on state)
STATUS                → STATE 0.000 0.000 1    (example; b=1 while blinking)
```

Invalid lines (each triggers exactly one ERR):

```text
FOO                   → ERR 1
target 0 0            → ERR 1   (lowercase)
TARGET x 0            → ERR 2   (bad token)
TARGET 0.0            → ERR 2   (missing arg)
TARGET 0 0 0          → ERR 2   (extra arg)
CENTER 0              → ERR 2   (extra arg)
TARGET  0 0           → ERR 2   (double space)
TARGET +1 0           → ERR 2   ("+1" malformed)
TARGET 00.5 0         → ERR 2   ("00.5" malformed)
TARGET .5 0           → ERR 2   (".5" malformed)
TARGET 1.0000 0       → ERR 2   (4 decimals)
TARGET 1.001 0        → ERR 3   (out of range)
TARGET 0 -1.5         → ERR 3   (out of range, well-formed)
(65-byte line)        → ERR 2   (length; then drain)
```

Startup sequence:

```text
(boot)                ← READY 1
TARGET 0.5 0.25       → OK
HEARTBEAT             →
STATUS                → STATE 0.500 0.250 0
```

Link-loss and recovery:

```text
HEARTBEAT             →          (t≈0 s)
(no traffic for ≥3 s)  → firmware recenters; blink continues
HEARTBEAT             →          (recovery)
                      ← READY 1   (emitted once)
STATUS                → STATE 0.000 0.000 0
```

## 14. Compliance checklist (normative summary)

| # | Requirement | Clause |
|---|---|---|
| 1 | Exactly one `\n` terminator; no `\r` | §4 |
| 2 | ≤ 64 B per line | §4, §9.4 |
| 3 | Closed grammar; unknown verb = ERR 1 | §6, §9.1 |
| 4 | Exact arity; arity error = ERR 2 | §6.2, §9.2 |
| 5 | `num` syntax, ≤3 decimals | §5, §9.2 |
| 6 | Range [−1,1]; range error = ERR 3 | §5, §9.2 |
| 7 | HEARTBEAT silent | §10.1 |
| 8 | Watchdog 3 s; any valid line resets it | §10.2 |
| 9 | Timeout → eased recenter; blink continues | §10.3 |
| 10 | Recovery → READY 1 once, no restart | §10.4 |
| 11 | STATE = commanded pose; no physical feedback | §8 |
| 12 | No CALIB, no degrees, no servo addressing | §12 |
| 13 | ERR order deterministic (single code per line) | §9.2 |

## 15. Ambiguities resolved during this stage

| # | Ambiguity found | Resolution (normative) |
|---|---|---|
| 1 | STATUS: does it return READY or STATE? | STATE. READY appears only at boot and once on watchdog recovery. Ratified by ADR-0003 amendment (2026-08-08). |
| 2 | Does HEARTBEAT receive an answer? | No response at all; it is silence by design (§10.1). |
| 3 | Empty line (`\n` only) — error or ignore? | Ignored silently (§9.5). |
| 4 | BLINK while mid-blink — queued? double? | Accepted with OK, discarded: no queue, no double-close (§11). |
| 5 | Multi-error line — which code wins? | First failing check in the fixed order (§9.2), exactly one ERR. |
| 6 | Over-length line with no `\n` — partial parse? | Never partial: drain to `\n`, one ERR 2 (§9.4). |
| 7 | Are `-0.000`, `1.` allowed? | `-0.000` → 0, valid; `1.` malformed (ERR 2); `+1` malformed (§5). |
| 8 | Do 1-second HEARTBEATs consume response bandwidth? | No: HEARTBEAT is silent; traffic stays 1 line/s (PC→F) + responses on demand. |
| 9 | Recenter vs `TARGET 0 0` — same thing? | No: CENTER is a firmware policy (eased); TARGET 0 0 is an explicit setpoint; behavior-equivalent when converged. |
| 10 | Who resets the watchdog in recovery — the first valid line | Any valid line (including HEARTBEAT) ends the timeout window; READY 1 is emitted exactly once (§10.4). |
| 11 | May the firmware emit unsolicited lines? | Only READY 1 at boot and once per recovery; nothing else (§7.2). |
| 12 | b flag semantics | 1 while blink FSM is in CLOSING/CLOSED/OPENING — exactly §8. |
| 13 | STATE blink field: optional (ADR brackets) or mandatory? | Mandatory — deterministic arity (`STATE x y b`); ADR-0003 brackets removed by amendment (2026-08-08). |

## 16. Versioning

- The protocol version is carried by `READY <n>`; v1.0 = `1`.
- Grammar changes (new verbs, new codes, changed semantics) bump the
  version and require an ADR before implementation (ADR-0003 discipline);
  the parsers and the golden corpus (Stage 3) are updated atomically with
  the spec (ADR-0008).
- Transport binding changes (new adapter) do NOT bump the version: the
  grammar stays authoritative.