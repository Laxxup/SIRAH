#include <cassert>

#include "../../calibration_commands.h"

using sirah::eyes::calibrator::Command;
using sirah::eyes::calibrator::CommandKind;
using sirah::eyes::calibrator::CalibrationSlot;
using sirah::eyes::calibrator::parse_command;
using sirah::eyes::calibrator::slot_channel;
using sirah::eyes::calibrator::slot_name;

int main() {
  Command command{};

  assert(parse_command("SET 4 145", &command));
  assert(command.kind == CommandKind::Set);
  assert(command.channel == 4);
  assert(command.angle == 145);

  assert(parse_command("SET X 110", &command));
  assert(command.kind == CommandKind::Set);
  assert(command.channel == 0);
  assert(command.angle == 110);

  assert(parse_command("X110", &command));
  assert(command.kind == CommandKind::Set);
  assert(command.channel == 0);
  assert(command.angle == 110);

  assert(parse_command("SD 90", &command));
  assert(command.kind == CommandKind::Set);
  assert(command.channel == 2);
  assert(command.angle == 90);

  assert(parse_command("ARM", &command));
  assert(command.kind == CommandKind::Arm);

  assert(parse_command("DISARM", &command));
  assert(command.kind == CommandKind::Disarm);

  assert(parse_command("SAVE", &command));
  assert(command.kind == CommandKind::SaveProfile);

  assert(parse_command("SAVE EYE_X_CENTER", &command));
  assert(command.kind == CommandKind::SaveSlot);
  assert(command.slot == CalibrationSlot::EyeXCenter);
  assert(slot_channel(command.slot) == 0);
  assert(std::strcmp(slot_name(command.slot), "EYE_X_CENTER") == 0);

  assert(parse_command("SAVE INF_LEFT_OPEN", &command));
  assert(command.slot == CalibrationSlot::InfLeftOpen);
  assert(slot_channel(command.slot) == 5);

  assert(parse_command("EXPORT", &command));
  assert(command.kind == CommandKind::Export);

  assert(parse_command("LOAD", &command));
  assert(command.kind == CommandKind::Load);

  assert(parse_command("SHOW", &command));
  assert(command.kind == CommandKind::Show);

  assert(parse_command("CENTER", &command));
  assert(command.kind == CommandKind::Center);

  assert(parse_command("HELP", &command));
  assert(command.kind == CommandKind::Help);

  assert(!parse_command("SET 6 90", &command));
  assert(!parse_command("SET 0 181", &command));
  assert(!parse_command("SET 0 -1", &command));
  assert(!parse_command("X181", &command));
  assert(!parse_command("SET Q 90", &command));
  assert(!parse_command("SAVE EYE_X_MIDDLE", &command));
  assert(!parse_command("UNKNOWN", &command));
}
