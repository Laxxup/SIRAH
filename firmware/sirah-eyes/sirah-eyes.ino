// Arduino sketch entrypoint. Device logic remains in platform/main.ino so
// host-testable core sources stay shared with the firmware build.
#include "platform/main.ino"
#include "core/protocol.cpp"
#include "core/mapping.cpp"
#include "core/easing.cpp"
#include "core/blink_fsm.cpp"
#include "platform/servo_driver.cpp"
