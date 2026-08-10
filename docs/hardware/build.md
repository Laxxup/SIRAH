# Hardware Build

This repository controls SIRAH's eyes subsystem: an ESP32, PCA9685 and six
servos. Consult `pin-map.md` before changing wiring or calibration.

## Power And Wiring

- Connect PCA9685 at I2C address `0x40` using the pins declared in
  `firmware/sirah-eyes/platform/pins.h`.
- Connect the six servos only to the channels in `config/actuators.yaml`.
- Power servos from an external regulated 5 V rail sized for their stall load.
- Join the external supply ground, PCA9685 ground and ESP32 ground.
- Do not power the servo rail from the ESP32 USB connection. Brownouts can
  reset the controller while a servo is under load.

## Runtime

The serial device must be `/dev/ttyUSB*` or `/dev/sirah-eyes`. Begin disarmed,
then use `sirah-runtime --eyes`. Stop and remove servo power before changing
wiring.
