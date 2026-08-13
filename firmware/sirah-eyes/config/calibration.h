#pragma once

// Physical limits and calibration corners — firmware is the AUTHORITY
// (ADR-0003/0004; decision A9: one source of truth for physical limits).
//
// Values measured manually with the current hardware setup on 2026-08-12.
// NO invented limits. Re-verify after any mechanical intervention.
//
// Sign conventions (A1): X normalized −1 left / 0 center / +1 right;
// Y −1 down / 0 center / +1 up. Physical servo inversion lives in
// calibration/config (direction field), never in behavior.

namespace sirah::eyes::calibration {

// PWM convention from legacy hardware: 500–2400 µs.
inline constexpr int kPwmUsMin = 500;
inline constexpr int kPwmUsMax = 2400;

// Eye X — degrees (left / center / right). Larger angle is left.
inline constexpr float kEyeXLeftDeg = 150.0F;
inline constexpr float kEyeXCenterDeg = 110.0F;
inline constexpr float kEyeXRightDeg = 50.0F;

// Eye Y — degrees (up / center / down).
inline constexpr float kEyeYUpDeg = 110.0F;
inline constexpr float kEyeYCenterDeg = 70.0F;
inline constexpr float kEyeYDownDeg = 40.0F;

// Eyelids — open / closed (degrees).
inline constexpr float kEyelidSupRightOpenDeg = 157.0F;
inline constexpr float kEyelidSupRightClosedDeg = 80.0F;
inline constexpr float kEyelidInfRightOpenDeg = 20.0F;
inline constexpr float kEyelidInfRightClosedDeg = 69.0F;
inline constexpr float kEyelidSupLeftOpenDeg = 87.0F;
inline constexpr float kEyelidSupLeftClosedDeg = 150.0F;
inline constexpr float kEyelidInfLeftOpenDeg = 130.0F;
inline constexpr float kEyelidInfLeftClosedDeg = 70.0F;

}  // namespace sirah::eyes::calibration
