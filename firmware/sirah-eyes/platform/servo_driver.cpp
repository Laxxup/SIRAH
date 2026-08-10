#include "platform/servo_driver.h"

#include <Wire.h>

namespace sirah::eyes::platform {

namespace {
using sirah::eyes::calibration::kPwmUsMax;
using sirah::eyes::calibration::kPwmUsMin;

constexpr float kServoFreqHz = 50.0F;
// 12-bit counter (4096) over one full PWM period at 50 Hz (20 ms).
constexpr float kCounterUs = 4096.0F / (1.0e6F / kServoFreqHz);
}  // namespace

void ServoDriver::init() {
  Wire.begin(kPwmI2cSda, kPwmI2cScl);
  pwm_ = Adafruit_PWMServoDriver(kPwmI2cAddr);
  pwm_.begin();
  pwm_.setPWMFreq(static_cast<int>(kServoFreqHz));

  set_eye_x(sirah::eyes::calibration::kEyeXCenterDeg);
  set_eye_y(sirah::eyes::calibration::kEyeYCenterDeg);
  set_eyelids(0.0F);
}

void ServoDriver::write_servo(int channel, float deg) {
  deg = deg < 0.0F ? 0.0F : (deg > 180.0F ? 180.0F : deg);
  const float us = kPwmUsMin + deg / 180.0F * (kPwmUsMax - kPwmUsMin);
  const uint16_t counter = static_cast<uint16_t>(us * kCounterUs);
  pwm_.setPWM(channel, 0, counter);
}

void ServoDriver::set_eye_x(float deg) {
  write_servo(kPwmChannelEyeX, sirah::eyes::core::clamp_deg_x(deg));
}

void ServoDriver::set_eye_y(float deg) {
  write_servo(kPwmChannelEyeY, sirah::eyes::core::clamp_deg_y(deg));
}

void ServoDriver::set_eyelid(EyelidId id, float progress) {
  switch (id) {
    case EyelidId::SupRight:
      write_servo(kPwmChannelEyelidSupRight,
                  sirah::eyes::core::kEyelidSupRight.position(progress));
      break;
    case EyelidId::InfRight:
      write_servo(kPwmChannelEyelidInfRight,
                  sirah::eyes::core::kEyelidInfRight.position(progress));
      break;
    case EyelidId::SupLeft:
      write_servo(kPwmChannelEyelidSupLeft,
                  sirah::eyes::core::kEyelidSupLeft.position(progress));
      break;
    case EyelidId::InfLeft:
      write_servo(kPwmChannelEyelidInfLeft,
                  sirah::eyes::core::kEyelidInfLeft.position(progress));
      break;
  }
}

void ServoDriver::set_eyelids(float progress) {
  set_eyelid(EyelidId::SupRight, progress);
  set_eyelid(EyelidId::InfRight, progress);
  set_eyelid(EyelidId::SupLeft, progress);
  set_eyelid(EyelidId::InfLeft, progress);
}

}  // namespace sirah::eyes::platform