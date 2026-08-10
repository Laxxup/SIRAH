# Calibration

`firmware/sirah-eyes/config/calibration.h` is the physical authority.
`config/actuators.yaml` mirrors it for the runtime.

1. Disarm the eyes and place the mechanism where it cannot bind.
2. Change one physical limit in `calibration.h`.
3. Run firmware host tests.
4. Mirror the value in `actuators.yaml`.
5. Run `sirah-calibrate validate` and the Python test suite.
6. Record the date, hardware revision and observed limits in `pin-map.md`.

Never introduce a serial calibration command. Limits remain firmware-owned.
