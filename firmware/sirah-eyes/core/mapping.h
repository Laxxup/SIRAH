// Normalized gaze -> servo degrees (A1 conventions) + hard clamps.
//
// Calibration values come EXCLUSIVELY from config/calibration.h (the
// registered hardware asset); this module never invents limits.
// Physical servo inversion (direction/offset/scale) is calibration data
// with identity in v0.3.0; the piecewise mapping below implements the
// A1 signs: X -1 left / 0 center / +1 right; Y -1 down / 0 center /
// +1 up.

#pragma once

#include "config/calibration.h"

namespace sirah::eyes::core {

// Piecewise-linear map through (n0,d0),(n1,d1),(n2,d2) with n0<=n1<=n2.
// n is clamped to [n0,n2] first; output is clamped to the degree range
// spanned by the three corners (hard clamp, ADR-0004).
float piecewise_map(float n, float n0, float d0, float n1, float d1, float n2,
                    float d2);

inline float map_eye_x(float n) {
  return piecewise_map(n, -1.0F, calibration::kEyeXLeftDeg, 0.0F,
                       calibration::kEyeXCenterDeg, 1.0F,
                       calibration::kEyeXRightDeg);
}

inline float map_eye_y(float n) {
  return piecewise_map(n, -1.0F, calibration::kEyeYDownDeg, 0.0F,
                       calibration::kEyeYCenterDeg, 1.0F,
                       calibration::kEyeYUpDeg);
}

// Degree-range hard clamps per axis (spanned by the registered corners).
inline float clamp_deg_x(float deg) {
  if (deg < calibration::kEyeXRightDeg) return calibration::kEyeXRightDeg;
  if (deg > calibration::kEyeXLeftDeg) return calibration::kEyeXLeftDeg;
  return deg;
}

inline float clamp_deg_y(float deg) {
  if (deg < calibration::kEyeYDownDeg) return calibration::kEyeYDownDeg;
  if (deg > calibration::kEyeYUpDeg) return calibration::kEyeYUpDeg;
  return deg;
}

// Eyelid: linear interpolation between the registered open/closed corners.
struct EyelidMove {
  float open_deg;
  float closed_deg;

  // t in [0,1]: 0 = fully open, 1 = fully closed.
  float position(float t) const;
  float clamp(float deg) const;
};

inline EyelidMove eyelid_move(float open_deg, float closed_deg) {
  return {open_deg, closed_deg};
}

// The four registered eyelid movements use only open/closed corners.
constexpr const EyelidMove kEyelidSupRight = EyelidMove{calibration::kEyelidSupRightOpenDeg, calibration::kEyelidSupRightClosedDeg};
constexpr const EyelidMove kEyelidInfRight = EyelidMove{calibration::kEyelidInfRightOpenDeg, calibration::kEyelidInfRightClosedDeg};
constexpr const EyelidMove kEyelidSupLeft = EyelidMove{calibration::kEyelidSupLeftOpenDeg, calibration::kEyelidSupLeftClosedDeg};
constexpr const EyelidMove kEyelidInfLeft = EyelidMove{calibration::kEyelidInfLeftOpenDeg, calibration::kEyelidInfLeftClosedDeg};

}  // namespace sirah::eyes::core
