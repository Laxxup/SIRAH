#pragma once

// Working hardware map (ADR-0011): servos ride on PCA9685 (0x40), driven
// over I2C from the ESP32. VERIFIED physically on 2026-08-09 (director,
// manual sweep via calibrator: all six actuators respond on CH0-CH5).
//
// External 5 V supply + common GND for the servo rail; the ESP32 stays on
// USB power for logic/flashing only (brownout evidence 2026-08-09).

namespace sirah::eyes::platform {

inline constexpr int kPwmI2cSda = 21;                // ESP32 GPIO21 -> PCA9685 SDA
inline constexpr int kPwmI2cScl = 22;                // ESP32 GPIO22 -> PCA9685 SCL
inline constexpr int kPwmI2cAddr = 0x40;             // PCA9685 address (A5-A0 open)

inline constexpr int kPwmChannelEyeX = 0;            // Ojo X (horizontal)
inline constexpr int kPwmChannelEyeY = 1;            // Ojo Y (vertical)
inline constexpr int kPwmChannelEyelidSupRight = 2;  // Párpado superior derecho
inline constexpr int kPwmChannelEyelidInfRight = 3;  // Párpado inferior derecho
inline constexpr int kPwmChannelEyelidSupLeft = 4;   // Párpado superior izquierdo
inline constexpr int kPwmChannelEyelidInfLeft = 5;   // Párpado inferior izquierdo

}  // namespace sirah::eyes::platform