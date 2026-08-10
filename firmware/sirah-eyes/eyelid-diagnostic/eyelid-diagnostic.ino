#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

#include "../config/calibration.h"
#include "../platform/pins.h"

namespace {

using namespace sirah::eyes;

constexpr float kServoFreqHz = 50.0F;
constexpr float kCounterUs = 4096.0F / (1.0e6F / kServoFreqHz);

Adafruit_PWMServoDriver pwm(platform::kPwmI2cAddr);

void write_servo(int channel, float degrees) {
  const float bounded = constrain(degrees, 0.0F, 180.0F);
  const float pulse_us = calibration::kPwmUsMin + bounded / 180.0F *
      (calibration::kPwmUsMax - calibration::kPwmUsMin);
  pwm.setPWM(channel, 0, static_cast<uint16_t>(pulse_us * kCounterUs));
}

void open_eyelids() {
  write_servo(platform::kPwmChannelEyelidSupRight,
              calibration::kEyelidSupRightOpenDeg);
  write_servo(platform::kPwmChannelEyelidInfRight,
              calibration::kEyelidInfRightOpenDeg);
  write_servo(platform::kPwmChannelEyelidSupLeft,
              calibration::kEyelidSupLeftOpenDeg);
  write_servo(platform::kPwmChannelEyelidInfLeft,
              calibration::kEyelidInfLeftOpenDeg);
}

void close_eyelids() {
  write_servo(platform::kPwmChannelEyelidSupRight,
              calibration::kEyelidSupRightClosedDeg);
  write_servo(platform::kPwmChannelEyelidInfRight,
              calibration::kEyelidInfRightClosedDeg);
  write_servo(platform::kPwmChannelEyelidSupLeft,
              calibration::kEyelidSupLeftClosedDeg);
  write_servo(platform::kPwmChannelEyelidInfLeft,
              calibration::kEyelidInfLeftClosedDeg);
}

void center_eyes() {
  write_servo(platform::kPwmChannelEyeX, calibration::kEyeXCenterDeg);
  write_servo(platform::kPwmChannelEyeY, calibration::kEyeYCenterDeg);
}

void handle_command(char command) {
  if (command == 'O') {
    open_eyelids();
    Serial.println("OPEN");
  } else if (command == 'C') {
    close_eyelids();
    Serial.println("CLOSED");
  } else if (command == 'B') {
    close_eyelids();
    delay(300);
    open_eyelids();
    Serial.println("BLINK");
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Wire.begin(platform::kPwmI2cSda, platform::kPwmI2cScl);
  pwm.begin();
  pwm.setPWMFreq(static_cast<int>(kServoFreqHz));
  center_eyes();
  open_eyelids();
  Serial.println("EYELID_DIAGNOSTIC READY: O=open C=close B=blink");
}

void loop() {
  while (Serial.available()) {
    const char command = static_cast<char>(Serial.read());
    if (command != '\n' && command != '\r') {
      handle_command(command);
    }
  }
}
