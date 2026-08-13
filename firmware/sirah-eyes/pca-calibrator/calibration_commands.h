#pragma once

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace sirah::eyes::calibrator {

enum class CalibrationSlot {
  EyeXLeft,
  EyeXCenter,
  EyeXRight,
  EyeYUp,
  EyeYCenter,
  EyeYDown,
  SupRightOpen,
  SupRightClosed,
  InfRightOpen,
  InfRightClosed,
  SupLeftOpen,
  SupLeftClosed,
  InfLeftOpen,
  InfLeftClosed,
  Count,
};

enum class CommandKind {
  Set,
  SaveProfile,
  SaveSlot,
  Load,
  Show,
  Export,
  Center,
  Help,
  Arm,
  Disarm,
};

struct Command {
  CommandKind kind;
  int channel;
  int angle;
  CalibrationSlot slot;
};

inline constexpr int kCalibrationSlotCount = static_cast<int>(CalibrationSlot::Count);

inline int slot_channel(CalibrationSlot slot) {
  switch (slot) {
    case CalibrationSlot::EyeXLeft:
    case CalibrationSlot::EyeXCenter:
    case CalibrationSlot::EyeXRight:
      return 0;
    case CalibrationSlot::EyeYUp:
    case CalibrationSlot::EyeYCenter:
    case CalibrationSlot::EyeYDown:
      return 1;
    case CalibrationSlot::SupRightOpen:
    case CalibrationSlot::SupRightClosed:
      return 2;
    case CalibrationSlot::InfRightOpen:
    case CalibrationSlot::InfRightClosed:
      return 3;
    case CalibrationSlot::SupLeftOpen:
    case CalibrationSlot::SupLeftClosed:
      return 4;
    case CalibrationSlot::InfLeftOpen:
    case CalibrationSlot::InfLeftClosed:
      return 5;
    case CalibrationSlot::Count:
      return -1;
  }
  return -1;
}

inline const char* slot_name(CalibrationSlot slot) {
  static constexpr const char* kNames[kCalibrationSlotCount] = {
      "EYE_X_LEFT",       "EYE_X_CENTER",      "EYE_X_RIGHT",      "EYE_Y_UP",
      "EYE_Y_CENTER",     "EYE_Y_DOWN",        "SUP_RIGHT_OPEN",   "SUP_RIGHT_CLOSED",
      "INF_RIGHT_OPEN",   "INF_RIGHT_CLOSED",  "SUP_LEFT_OPEN",    "SUP_LEFT_CLOSED",
      "INF_LEFT_OPEN",    "INF_LEFT_CLOSED",
  };
  const int index = static_cast<int>(slot);
  return index >= 0 && index < kCalibrationSlotCount ? kNames[index] : "UNKNOWN";
}

inline bool parse_slot(const char* name, CalibrationSlot* slot) {
  if (name == nullptr || slot == nullptr) return false;
  for (int index = 0; index < kCalibrationSlotCount; ++index) {
    const auto candidate = static_cast<CalibrationSlot>(index);
    if (std::strcmp(name, slot_name(candidate)) == 0) {
      *slot = candidate;
      return true;
    }
  }
  return false;
}

inline bool parse_named_channel_command(const char* actuator, int angle, Command* command) {
  if (std::strcmp(actuator, "X") == 0) {
    *command = Command{CommandKind::Set, 0, angle, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(actuator, "Y") == 0) {
    *command = Command{CommandKind::Set, 1, angle, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(actuator, "SD") == 0) {
    *command = Command{CommandKind::Set, 2, angle, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(actuator, "ID") == 0) {
    *command = Command{CommandKind::Set, 3, angle, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(actuator, "SI") == 0) {
    *command = Command{CommandKind::Set, 4, angle, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(actuator, "II") == 0) {
    *command = Command{CommandKind::Set, 5, angle, CalibrationSlot::Count};
    return true;
  }
  return false;
}

inline bool parse_channel_command(const char* line, const char* name, int channel,
                                  Command* command) {
  const size_t name_length = std::strlen(name);
  if (std::strncmp(line, name, name_length) != 0) return false;

  const char* angle_text = line + name_length;
  while (*angle_text != '\0' && std::isspace(static_cast<unsigned char>(*angle_text))) {
    ++angle_text;
  }
  if (*angle_text == '\0') return false;

  char* end = nullptr;
  const long angle = std::strtol(angle_text, &end, 10);
  while (end != nullptr && *end != '\0' && std::isspace(static_cast<unsigned char>(*end))) {
    ++end;
  }
  if (end == angle_text || (end != nullptr && *end != '\0') || angle < 0 || angle > 180) {
    return false;
  }

  *command = Command{CommandKind::Set, channel, static_cast<int>(angle), CalibrationSlot::Count};
  return true;
}

inline bool parse_command(const char* line, Command* command) {
  if (line == nullptr || command == nullptr) return false;

  int channel = 0;
  int angle = 0;
  char extra = '\0';
  if (std::sscanf(line, "SET %d %d %c", &channel, &angle, &extra) == 2) {
    if (channel < 0 || channel > 5 || angle < 0 || angle > 180) return false;
    *command = Command{CommandKind::Set, channel, angle, CalibrationSlot::Count};
    return true;
  }

  char actuator[3] = {};
  if (std::sscanf(line, "SET %2s %d %c", actuator, &angle, &extra) == 2) {
    if (angle < 0 || angle > 180) return false;
    return parse_named_channel_command(actuator, angle, command);
  }

  if (parse_channel_command(line, "SD", 2, command) ||
      parse_channel_command(line, "ID", 3, command) ||
      parse_channel_command(line, "SI", 4, command) ||
      parse_channel_command(line, "II", 5, command) ||
      parse_channel_command(line, "X", 0, command) ||
      parse_channel_command(line, "Y", 1, command)) {
    return true;
  }

  if (std::strcmp(line, "SAVE") == 0) {
    *command = Command{CommandKind::SaveProfile, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strncmp(line, "SAVE ", 5) == 0) {
    CalibrationSlot slot{};
    if (!parse_slot(line + 5, &slot)) return false;
    *command = Command{CommandKind::SaveSlot, slot_channel(slot), 0, slot};
    return true;
  }
  if (std::strcmp(line, "LOAD") == 0) {
    *command = Command{CommandKind::Load, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "SHOW") == 0) {
    *command = Command{CommandKind::Show, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "EXPORT") == 0) {
    *command = Command{CommandKind::Export, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "CENTER") == 0) {
    *command = Command{CommandKind::Center, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "HELP") == 0) {
    *command = Command{CommandKind::Help, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "ARM") == 0) {
    *command = Command{CommandKind::Arm, 0, 0, CalibrationSlot::Count};
    return true;
  }
  if (std::strcmp(line, "DISARM") == 0) {
    *command = Command{CommandKind::Disarm, 0, 0, CalibrationSlot::Count};
    return true;
  }
  return false;
}

}  // namespace sirah::eyes::calibrator
