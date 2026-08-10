// Actuator driver: thin, dumb PWM wrapper over PCA9685 (ADR-0011; device
// build only — this file is NOT part of the host build; it requires
// Arduino + Adafruit_PWMServoDriver).
//
// All safety logic (hard clamps, ADR-0004) lives in core; this layer only
// writes PWM channels. Calibration authority: config/calibration.h.

#pragma once

#include <Adafruit_PWMServoDriver.h>

#include "config/calibration.h"
#include "core/mapping.h"
#include "platform/pins.h"

namespace sirah::eyes::platform {

enum class EyelidId { SupRight, InfRight, SupLeft, InfLeft };

class ServoDriver {
 public:
  // Begins the PCA9685 (I2C, 50 Hz) and parks all six actuators at the
  // center/open pose.
  void init();

  // Degrees in, hard-clamped again (defense in depth), PWM out.
  void set_eye_x(float deg);
  void set_eye_y(float deg);

  // progress in [0,1]: 0 fully open, 1 fully closed.
  void set_eyelid(EyelidId id, float progress);
  void set_eyelids(float progress);

 private:
  // Maps a servo angle to the PCA9685 12-bit ON-counter and writes it.
  void write_servo(int channel, float deg);

  Adafruit_PWMServoDriver pwm_;
};

}  // namespace sirah::eyes::platform