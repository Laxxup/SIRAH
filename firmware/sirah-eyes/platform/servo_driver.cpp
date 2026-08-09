#include "platform/servo_driver.h"

namespace sirah::eyes::platform {

namespace {
using sirah::eyes::calibration::kPwmUsMax;
using sirah::eyes::calibration::kPwmUsMin;

constexpr int kUsPerDeg = (kPwmUsMax - kPwmUsMin) / 180;
}  // namespace

void ServoDriver::init() {
  eye_x_.attach(kPinEyeX, kPwmUsMin, kPwmUsMax);
  eye_y_.attach(kPinEyeY, kPwmUsMin, kPwmUsMax);
  sup_r_.attach(kPinEyelidSupRight, kPwmUsMin, kPwmUsMax);
  inf_r_.attach(kPinEyelidInfRight, kPwmUsMin, kPwmUsMax);
  sup_l_.attach(kPinEyelidSupLeft, kPwmUsMin, kPwmUsMax);
  inf_l_.attach(kPinEyelidInfLeft, kPwmUsMin, kPwmUsMax);

  set_eye_x(sirah::eyes::calibration::kEyeXCenterDeg);
  set_eye_y(sirah::eyes::calibration::kEyeYCenterDeg);
  set_eyelids(0.0F);
}

void ServoDriver::set_eye_x(float deg) {
  eye_x_.write(sirah::eyes::core::clamp_deg_x(deg));
}

void ServoDriver::set_eye_y(float deg) {
  eye_y_.write(sirah::eyes::core::clamp_deg_y(deg));
}

void ServoDriver::set_eyelid(EyelidId id, float progress) {
  switch (id) {
    case EyelidId::SupRight:
      sup_r_.write(sirah::eyes::core::kEyelidSupRight.position(progress));
      break;
    case EyelidId::InfRight:
      inf_r_.write(sirah::eyes::core::kEyelidInfRight.position(progress));
      break;
    case EyelidId::SupLeft:
      sup_l_.write(sirah::eyes::core::kEyelidSupLeft.position(progress));
      break;
    case EyelidId::InfLeft:
      inf_l_.write(sirah::eyes::core::kEyelidInfLeft.position(progress));
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