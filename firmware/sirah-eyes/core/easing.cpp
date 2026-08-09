#include "core/easing.h"

#include <cstdlib>

namespace sirah::eyes::core {

namespace {
constexpr float kSnapEps = 0.001F;
}  // namespace

bool GazeEaser::tick(float target_x, float target_y, float kx, float ky) {
  x += (target_x - x) * kx;
  y += (target_y - y) * ky;
  bool settled = true;
  if (std::abs(target_x - x) < kSnapEps) {
    x = target_x;
  } else {
    settled = false;
  }
  if (std::abs(target_y - y) < kSnapEps) {
    y = target_y;
  } else {
    settled = false;
  }
  return settled;
}

}  // namespace sirah::eyes::core