#pragma once

// WORKING pin map (A5, director 2026-08-08) — NOT definitive evidence.
//
// Stage 4 of the implementation plan MUST verify every actuator
// physically via sweep and record the truth in docs/hardware/pin-map.md.
// If the sweep contradicts this map, PHYSICAL EVIDENCE WINS.
//
// Source record:
//   sirah-architecture-study/reports/hardware/initial-calibration-2026-08-08.md

namespace sirah::eyes::platform {

inline constexpr int kPinEyeX = 25;              // Ojo X (horizontal)
inline constexpr int kPinEyeY = 26;              // Ojo Y (vertical)
inline constexpr int kPinEyelidSupRight = 14;    // Párpado superior derecho
inline constexpr int kPinEyelidInfRight = 27;    // Párpado inferior derecho
inline constexpr int kPinEyelidInfLeft = 32;     // Párpado inferior izquierdo
inline constexpr int kPinEyelidSupLeft = 33;     // Párpado superior izquierdo

}  // namespace sirah::eyes::platform