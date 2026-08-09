// Stage 1 placeholder host test: proves the skeleton compiles and runs
// with plain g++ (no Arduino). Real tests arrive in later stages
// (mapping, blink FSM, parser — ADR-0010).

#include <cassert>

#include "config/calibration.h"
#include "platform/pins.h"

int main() {
  static_assert(sirah::eyes::platform::kPinEyeX == 25);
  assert(sirah::eyes::calibration::kEyeXCenterDeg == 130.0F);
  return 0;
}