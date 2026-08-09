# SIRAH eyes — ESP32 firmware skeleton (Stage 1)

Structure only. The wire contract is a placeholder until Stage 2; no
production firmware logic exists at this stage.

```
core/       Pure C++ (Arduino-free), host-testable with g++ (ADR-0010)
platform/   pins.h — WORKING pin map (A5); later: servo driver, main.ino
config/     calibration.h — limits from the calibration record (authority)
tests/host/ Host test build (plain g++, no Arduino)
```

Host tests: `make -C tests/host` compiles and runs with g++ only.
No PlatformIO dependency in Stage 1 (toolchain decision P3 still pending
director approval; plan documents the host-g++ requirement).

## Safety authority

`config/calibration.h` holds the physical limits. It is the firmware
authority (ADR-0003/0004/A9): the runtime config is a mirror validated by
a consistency test, never a second authority.