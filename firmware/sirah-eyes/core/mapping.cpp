#include "core/mapping.h"

namespace sirah::eyes::core {

namespace {
float clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}
}  // namespace

float piecewise_map(float n, float n0, float d0, float n1, float d1, float n2,
                    float d2) {
  n = clampf(n, n0, n2);
  float deg;
  if (n <= n1) {
    deg = d0 + (n - n0) * (d1 - d0) / (n1 - n0);
  } else {
    deg = d1 + (n - n1) * (d2 - d1) / (n2 - n1);
  }
  const float lo = d0 < d2 ? d0 : d2;
  const float hi = d0 > d2 ? d0 : d2;
  return clampf(deg, lo, hi);
}

float EyelidMove::position(float t) const {
  t = clampf(t, 0.0F, 1.0F);
  return open_deg + (closed_deg - open_deg) * t;
}

float EyelidMove::clamp(float deg) const {
  const float lo = open_deg < closed_deg ? open_deg : closed_deg;
  const float hi = open_deg > closed_deg ? open_deg : closed_deg;
  return clampf(deg, lo, hi);
}

}  // namespace sirah::eyes::core