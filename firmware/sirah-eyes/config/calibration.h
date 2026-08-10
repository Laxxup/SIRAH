#pragma once

// Physical limits and calibration corners — firmware is the AUTHORITY
// (ADR-0003/0004; decision A9: one source of truth for physical limits).
//
// Values from the verified calibration record (director, manual sweep via
// PCA9685, 2026-08-09; evidence class VERIFIED — V6.12 final).
// NO invented limits. Stage 4 re-verifies corners on hardware and updates
// this file if the measured values differ.
//
// Sign conventions (A1): X normalized −1 left / 0 center / +1 right;
// Y −1 down / 0 center / +1 up. Physical servo inversion lives in
// calibration/config (direction field), never in behavior.

namespace sirah::eyes::calibration {

// PWM convention from legacy hardware: 500–2400 µs.
inline constexpr int kPwmUsMin = 500;
inline constexpr int kPwmUsMax = 2400;

// Eye X — degrees (left / center / right). Verified: left 140, center
// 110, right 70 (inverted range: larger angle = left, A1 sign handled by
// the mapping below, physical inversion lives in calibration data).
inline constexpr float kEyeXLeftDeg = 140.0F;
inline constexpr float kEyeXCenterDeg = 110.0F;
inline constexpr float kEyeXRightDeg = 70.0F;

// Eye Y — degrees (up / center / down).
inline constexpr float kEyeYUpDeg = 85.0F;
inline constexpr float kEyeYCenterDeg = 75.0F;
inline constexpr float kEyeYDownDeg = 60.0F;

// Eyelids — open / closed (degrees).
inline constexpr float kEyelidSupRightOpenDeg = 110.0F;
inline constexpr float kEyelidSupRightClosedDeg = 70.0F;
inline constexpr float kEyelidInfRightOpenDeg = 10.0F;
inline constexpr float kEyelidInfRightClosedDeg = 70.0F;
inline constexpr float kEyelidSupLeftOpenDeg = 145.0F;
inline constexpr float kEyelidSupLeftClosedDeg = 170.0F;
inline constexpr float kEyelidInfLeftOpenDeg = 95.0F;
inline constexpr float kEyelidInfLeftClosedDeg = 40.0F;

// Squint pose ("entrecerrado") — degrees (inf/sup, right/left).
inline constexpr float kSquintInfRightDeg = 30.0F;
inline constexpr float kSquintSupRightDeg = 90.0F;
inline constexpr float kSquintInfLeftDeg = 70.0F;
inline constexpr float kSquintSupLeftDeg = 146.0F;

}  // namespace sirah::eyes::calibration