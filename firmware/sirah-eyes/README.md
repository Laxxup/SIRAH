# SIRAH eyes — ESP32 firmware (Stage 4: 6-actuator core)

```
core/       Pure C++ (Arduino-free), host-testable with g++ (ADR-0010)
platform/   pins.h (A5 working map), servo_driver.{h,cpp}, main.ino
config/     calibration.h — limits from the calibration record (authority)
tests/host/ core_tests.cpp + Makefile (plain g++, no Arduino)
```

Stage 4 contents:

- `core/protocol.{h,cpp}` — wire parser/serializers mirroring the Python
  parser, gated by the golden corpus (tests/contract, 91 cases).
- `core/mapping.{h,cpp}` — normalized -> degrees (A1 signs, ADR-0005) and
  hard clamps; calibration is the only limits authority.
- `core/easing.{h,cpp}` — per-axis exponential easing in normalized space
  (Y more damped, ADR-0005); no overshoot by construction.
- `core/blink_fsm.{h,cpp}` — firmware-owned blink FSM (ADR-0004/A10);
  cadence 6 s ± 2 s drawn by caller; mid-blink triggers discarded.
- `platform/servo_driver.{h,cpp}` — ESP32Servo wrapper (device only).
- `platform/main.ino` — Serial 115200, line protocol, 20 ms tick loop.

Host tests: `make -C tests/host` compiles and runs core tests with g++.
Contract gate: `make -C tests/host contract_checker` then
`./tests/host/build/contract_checker <golden-dir>` (exit 0 iff 91/91).

Prerequisites for device build (NOT installed here, decision P3 pending):
PlatformIO/Arduino-esp32. Stage 4 host gates run without it.

## Safety authority

`config/calibration.h` holds the physical limits. It is the firmware
authority (ADR-0003/0004/A9): the runtime config is a mirror validated by
a consistency test, never a second authority. `platform/pins.h` (A5) is a
working map pending the physical sweep (docs/hardware/pin-map.md): the
sweep evidence wins if it contradicts the map.