// Actuator driver: thin, dumb PWM wrapper (device build only — this file
// is NOT part of the host build; it requires Arduino + ESP32Servo).
//
// All safety logic (hard clamps, ADR-0004) lives in core; this layer only
// attaches/writes servos. Calibration authority: config/calibration.h.

#pragma once

#include <ESP32Servo.h>

#include "config/calibration.h"
#include "core/mapping.h"
#include "platform/pins.h"

namespace sirah::eyes::platform {

enum class EyelidId { SupRight, InfRight, SupLeft, InfLeft };

class ServoDriver {
 public:
  // Attaches all six servos (PWM 500-2400 us) and parks them at the
  // center/open pose.
  void init();

  // Degrees in, hard-clamped again (defense in depth), PWM out.
  void set_eye_x(float deg);
  void set_eye_y(float deg);

  // progress in [0,1]: 0 fully open, 1 fully closed.
  void set_eyelid(EyelidId id, float progress);
  void set_eyelids(float progress);

 private:
  Servo eye_x_;
  Servo eye_y_;
  Servo sup_r_;
  Servo inf_r_;
  Servo sup_l_;
  Servo inf_l_;
};

}  // namespace sirah::eyes::platform