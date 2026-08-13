#include <Adafruit_PWMServoDriver.h>
#include <Preferences.h>
#include <Wire.h>

#include "calibration_commands.h"

namespace {

constexpr uint8_t kPcaAddress = 0x40;
constexpr int kSdaPin = 21;
constexpr int kSclPin = 22;
constexpr int kServoCount = 6;
constexpr int kServoFrequencyHz = 50;
constexpr int kPulseUsMin = 500;
constexpr int kPulseUsMax = 2400;
constexpr int kDefaultAngles[kServoCount] = {110, 75, 110, 10, 145, 95};
constexpr size_t kLineCapacity = 48;
constexpr int kUnsetAngle = -1;

Adafruit_PWMServoDriver g_pca(kPcaAddress);
Preferences g_preferences;
int g_angles[kServoCount] = {};
int g_profile[sirah::eyes::calibrator::kCalibrationSlotCount] = {};
char g_line[kLineCapacity] = {};
size_t g_line_length = 0;
bool g_armed = false;
int g_selected_channel = -1;

uint16_t angle_to_ticks(int angle) {
  const long pulse_us = map(angle, 0, 180, kPulseUsMin, kPulseUsMax);
  return static_cast<uint16_t>((pulse_us * 4096L * kServoFrequencyHz + 500000L) / 1000000L);
}

void write_channel(int channel, int angle) {
  g_angles[channel] = angle;
  g_selected_channel = channel;
  g_pca.setPWM(channel, 0, angle_to_ticks(angle));
}

void turn_off_all() {
  for (int channel = 0; channel < kServoCount; ++channel) {
    g_pca.setPWM(channel, 0, 4096);
  }
}

void load_defaults() {
  for (int channel = 0; channel < kServoCount; ++channel) {
    g_angles[channel] = kDefaultAngles[channel];
  }
}

void clear_profile() {
  for (int slot = 0; slot < sirah::eyes::calibrator::kCalibrationSlotCount; ++slot) {
    g_profile[slot] = kUnsetAngle;
  }
}

void show_angles() {
  Serial.printf("STATE %s\n", g_armed ? "ARMED" : "DISARMED");
  for (int channel = 0; channel < kServoCount; ++channel) {
    Serial.printf("CH%d %d\n", channel, g_angles[channel]);
  }
  for (int slot = 0; slot < sirah::eyes::calibrator::kCalibrationSlotCount; ++slot) {
    const auto named_slot = static_cast<sirah::eyes::calibrator::CalibrationSlot>(slot);
    if (g_profile[slot] == kUnsetAngle) {
      Serial.printf("%s UNSET\n", sirah::eyes::calibrator::slot_name(named_slot));
    } else {
      Serial.printf("%s %d\n", sirah::eyes::calibrator::slot_name(named_slot), g_profile[slot]);
    }
  }
}

void print_help() {
  Serial.println("ARM / DISARM");
  Serial.println("X<angulo> Y<angulo> SD<angulo> ID<angulo> SI<angulo> II<angulo>");
  Serial.println("SET <canal 0-5> <angulo> / SET X|Y|SD|ID|SI|II <angulo>");
  Serial.println("SHOW");
  Serial.println("SAVE <ETIQUETA> / SAVE / LOAD / EXPORT");
  Serial.println("LOAD");
  Serial.println("CENTER");
  Serial.println("HELP");
}

void save_angles() {
  const size_t written = g_preferences.putBytes("profile", g_profile, sizeof(g_profile));
  Serial.println(written == sizeof(g_profile) ? "OK SAVED" : "ERR SAVE");
}

void load_angles() {
  if (g_preferences.getBytesLength("profile") != sizeof(g_profile)) {
    clear_profile();
    Serial.println("OK EMPTY PROFILE");
  } else {
    g_preferences.getBytes("profile", g_profile, sizeof(g_profile));
    Serial.println("OK PROFILE LOADED");
  }
}

bool profile_complete() {
  for (int slot = 0; slot < sirah::eyes::calibrator::kCalibrationSlotCount; ++slot) {
    if (g_profile[slot] == kUnsetAngle) return false;
  }
  return true;
}

void export_profile() {
  using sirah::eyes::calibrator::CalibrationSlot;
  if (!profile_complete()) {
    Serial.println("ERR INCOMPLETE PROFILE");
    for (int slot = 0; slot < sirah::eyes::calibrator::kCalibrationSlotCount; ++slot) {
      if (g_profile[slot] == kUnsetAngle) {
        Serial.printf("MISSING %s\n", sirah::eyes::calibrator::slot_name(static_cast<CalibrationSlot>(slot)));
      }
    }
    return;
  }
  Serial.println("CALIBRATION_H");
  Serial.printf("inline constexpr float kEyeXLeftDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeXLeft)]);
  Serial.printf("inline constexpr float kEyeXCenterDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeXCenter)]);
  Serial.printf("inline constexpr float kEyeXRightDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeXRight)]);
  Serial.printf("inline constexpr float kEyeYUpDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeYUp)]);
  Serial.printf("inline constexpr float kEyeYCenterDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeYCenter)]);
  Serial.printf("inline constexpr float kEyeYDownDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::EyeYDown)]);
  Serial.printf("inline constexpr float kEyelidSupRightOpenDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::SupRightOpen)]);
  Serial.printf("inline constexpr float kEyelidSupRightClosedDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::SupRightClosed)]);
  Serial.printf("inline constexpr float kEyelidInfRightOpenDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::InfRightOpen)]);
  Serial.printf("inline constexpr float kEyelidInfRightClosedDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::InfRightClosed)]);
  Serial.printf("inline constexpr float kEyelidSupLeftOpenDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::SupLeftOpen)]);
  Serial.printf("inline constexpr float kEyelidSupLeftClosedDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::SupLeftClosed)]);
  Serial.printf("inline constexpr float kEyelidInfLeftOpenDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::InfLeftOpen)]);
  Serial.printf("inline constexpr float kEyelidInfLeftClosedDeg = %d.0F;\n", g_profile[static_cast<int>(CalibrationSlot::InfLeftClosed)]);
  Serial.println("ACTUATORS_YAML");
  Serial.printf("eyes.x.left_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeXLeft)]);
  Serial.printf("eyes.x.center_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeXCenter)]);
  Serial.printf("eyes.x.right_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeXRight)]);
  Serial.printf("eyes.y.up_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeYUp)]);
  Serial.printf("eyes.y.center_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeYCenter)]);
  Serial.printf("eyes.y.down_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::EyeYDown)]);
  Serial.printf("eyelids.sup_right.open_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::SupRightOpen)]);
  Serial.printf("eyelids.sup_right.closed_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::SupRightClosed)]);
  Serial.printf("eyelids.inf_right.open_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::InfRightOpen)]);
  Serial.printf("eyelids.inf_right.closed_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::InfRightClosed)]);
  Serial.printf("eyelids.sup_left.open_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::SupLeftOpen)]);
  Serial.printf("eyelids.sup_left.closed_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::SupLeftClosed)]);
  Serial.printf("eyelids.inf_left.open_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::InfLeftOpen)]);
  Serial.printf("eyelids.inf_left.closed_deg: %d.0\n", g_profile[static_cast<int>(CalibrationSlot::InfLeftClosed)]);
}

void execute_command(const char* line) {
  using sirah::eyes::calibrator::Command;
  using sirah::eyes::calibrator::CommandKind;
  using sirah::eyes::calibrator::parse_command;

  Command command{};
  if (!parse_command(line, &command)) {
    Serial.println("ERR COMMAND");
    print_help();
    return;
  }

  switch (command.kind) {
    case CommandKind::Set:
      if (!g_armed) {
        Serial.println("ERR DISARMED; SEND ARM FIRST");
        break;
      }
      write_channel(command.channel, command.angle);
      Serial.printf("OK CH%d %d\n", command.channel, command.angle);
      break;
    case CommandKind::SaveSlot:
      if (!g_armed) {
        Serial.println("ERR DISARMED; SEND ARM FIRST");
      } else if (g_selected_channel != sirah::eyes::calibrator::slot_channel(command.slot)) {
        Serial.println("ERR SLOT CHANNEL");
      } else {
        g_profile[static_cast<int>(command.slot)] = g_angles[command.channel];
        Serial.printf("OK %s %d\n", sirah::eyes::calibrator::slot_name(command.slot), g_angles[command.channel]);
      }
      break;
    case CommandKind::SaveProfile:
      save_angles();
      break;
    case CommandKind::Load:
      load_angles();
      break;
    case CommandKind::Show:
      show_angles();
      break;
    case CommandKind::Export:
      export_profile();
      break;
    case CommandKind::Center:
      load_defaults();
      Serial.println("OK DEFAULTS");
      break;
    case CommandKind::Help:
      print_help();
      break;
    case CommandKind::Arm:
      g_armed = true;
      Serial.println("OK ARMED; SELECT A CHANNEL");
      break;
    case CommandKind::Disarm:
      turn_off_all();
      g_armed = false;
      g_selected_channel = -1;
      Serial.println("OK DISARMED");
      break;
  }
}

void read_serial() {
  while (Serial.available() > 0) {
    const char character = static_cast<char>(Serial.read());
    if (character == '\r') continue;
    if (character == '\n') {
      g_line[g_line_length] = '\0';
      if (g_line_length > 0) execute_command(g_line);
      g_line_length = 0;
    } else if (g_line_length < kLineCapacity - 1) {
      g_line[g_line_length++] = character;
    } else {
      g_line_length = 0;
      Serial.println("ERR LINE TOO LONG");
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Wire.begin(kSdaPin, kSclPin);
  g_pca.begin();
  g_pca.setPWMFreq(kServoFrequencyHz);
  turn_off_all();
  g_preferences.begin("sirah-cal", false);
  clear_profile();
  load_angles();
  Serial.println("SIRAH PCA CALIBRATOR READY: DISARMED");
  print_help();
}

void loop() {
  read_serial();
}
