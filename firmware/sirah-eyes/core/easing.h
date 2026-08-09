// Per-axis gaze easing (deterministic, no overshoot).
//
// X and Y move independently but update in the same tick, so they are
// capable of simultaneous motion. Y is intentionally more damped
// (ADR-0005). The easing happens in NORMALIZED space; the firmware maps
// to degrees at write time. The eased values are exactly what STATE
// carries on the wire (protocol.md 8).

#pragma once

namespace sirah::eyes::core {

struct GazeEaser {
  float x = 0.0F;  // normalized, A1 signs
  float y = 0.0F;

  // Drifts the current pose toward the target by one tick; snaps to the
  // target when within the epsilon. Returns true if the pose is settled
  // (== target, within epsilon) AFTER this tick. Exponentially smoothed:
  // no overshoot by construction (0 < k < 1, approach from one side).
  bool tick(float target_x, float target_y, float kx, float ky);
};

}  // namespace sirah::eyes::core