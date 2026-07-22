#include <ESP32Servo.h>

namespace {

constexpr int SERVO_PIN = 18;

constexpr float MIN_ANGLE_DEG = 0.0;
constexpr float MAX_ANGLE_DEG = 120.0;
constexpr float MIN_SPEED_DEG_S = 0.1;
constexpr float MAX_SPEED_DEG_S = 50.0;

Servo rightArm;

float currentAngle = 0.0;

bool isFiniteNumber(float value) {
  return !isnan(value) && !isinf(value);
}

void rejectCommand(const String& commandId, const String& reason) {
  Serial.print("REJECTED|");
  Serial.print(commandId);
  Serial.print("|");
  Serial.println(reason);
}

void applyPosition(
    const String& commandId,
    const String& target,
    float angleDeg,
    float speedDegS
) {
  if (target != "right_arm") {
    rejectCommand(commandId, "unknown_target");
    return;
  }

  if (!isFiniteNumber(angleDeg) ||
      angleDeg < MIN_ANGLE_DEG ||
      angleDeg > MAX_ANGLE_DEG) {
    rejectCommand(commandId, "angle_out_of_range");
    return;
  }

  if (!isFiniteNumber(speedDegS) ||
      speedDegS < MIN_SPEED_DEG_S ||
      speedDegS > MAX_SPEED_DEG_S) {
    rejectCommand(commandId, "speed_out_of_range");
    return;
  }

  Serial.print("ACCEPTED|");
  Serial.println(commandId);

  const float distance = abs(angleDeg - currentAngle);
  const unsigned long durationMs =
      static_cast<unsigned long>((distance / speedDegS) * 1000.0);

  const int direction = angleDeg >= currentAngle ? 1 : -1;
  float position = currentAngle;

  unsigned long lastStepAt = millis();

  while (abs(position - angleDeg) >= 1.0) {
    const unsigned long now = millis();

    if (now - lastStepAt >= 20) {
      position += direction * speedDegS * 0.020;

      if ((direction > 0 && position > angleDeg) ||
          (direction < 0 && position < angleDeg)) {
        position = angleDeg;
      }

      rightArm.write(static_cast<int>(position));
      lastStepAt = now;
    }
  }

  rightArm.write(static_cast<int>(angleDeg));
  currentAngle = angleDeg;

  Serial.print("APPLIED|");
  Serial.print(commandId);
  Serial.print("|");
  Serial.print(target);
  Serial.print("|");
  Serial.print(angleDeg, 1);
  Serial.print("|duration_ms=");
  Serial.println(durationMs);
}

void processCommand(String line) {
  line.trim();

  if (line.isEmpty()) {
    return;
  }

  // Formato:
  // SET_POSITION|command_id|target|angle_deg|speed_deg_s

  const int separator1 = line.indexOf('|');
  const int separator2 = line.indexOf('|', separator1 + 1);
  const int separator3 = line.indexOf('|', separator2 + 1);
  const int separator4 = line.indexOf('|', separator3 + 1);

  if (separator1 < 0 ||
      separator2 < 0 ||
      separator3 < 0 ||
      separator4 < 0) {
    rejectCommand("unknown", "malformed_command");
    return;
  }

  const String action = line.substring(0, separator1);
  const String commandId = line.substring(separator1 + 1, separator2);
  const String target = line.substring(separator2 + 1, separator3);
  const String angleText = line.substring(separator3 + 1, separator4);
  const String speedText = line.substring(separator4 + 1);

  if (action != "SET_POSITION") {
    rejectCommand(commandId, "unsupported_action");
    return;
  }

  if (commandId.isEmpty()) {
    rejectCommand("unknown", "missing_command_id");
    return;
  }

  const float angleDeg = angleText.toFloat();
  const float speedDegS = speedText.toFloat();

  applyPosition(
      commandId,
      target,
      angleDeg,
      speedDegS
  );
}

}  // namespace

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(100);

  rightArm.setPeriodHertz(50);
  rightArm.attach(SERVO_PIN, 500, 2400);
  rightArm.write(0);

  Serial.println("READY|sirah-velxio-preview");
  Serial.println("PROTOCOL|experimental-serial-v0");
  Serial.println("LIMITS|right_arm|angle=0..120|speed=0.1..50");
}

void loop() {
  if (Serial.available() > 0) {
    const String line = Serial.readStringUntil('\n');
    processCommand(line);
  }
}
