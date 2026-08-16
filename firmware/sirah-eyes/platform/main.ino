// SIRAH eyes — ESP32 firmware entry point (Stage 4; device build only).
// SIRAH = Sistema Inteligente Robótico de Asistencia Humana (in Spanish,
// never translated); this firmware serves the eyes subsystem.
//
// Responsibilities (ADR-0003/0004, A1/A10):
//   - Serial 115200, line framing per protocol.md v1.0 (63-byte payload,
//     overflow -> ERR 2 and drain), one response per command line.
//   - TARGET/CENTER: normalized gaze commands; eased to degrees by firmware.
//   - BLINK: best-effort punctual trigger for the firmware-owned blink FSM.
//   - STATUS: current eased gaze + blink flag. HEARTBEAT: accepted in
//     silence (keeps the watchdog alive, spec 10.1).
//   - Watchdog (spec 10, Stage 11): any VALID command line resets it
//     (spec 10.2); after 3 s without activity the link is considered lost
//     and the firmware eases to the safe pose CENTER and holds it while
//     the link stays down (spec 10.3). Blinking continues (ADR-0004). The
//     first valid line after a timeout recovers the link and emits
//     READY 1 exactly once (spec 10.4).
//   - Natural blinking cadence 6 s ± 2 s (A10), firmware-owned, jitter
//     drawn with esp_random() at every cycle start.
//   - Grammar stays closed (protocol.md v1.0): no verb beyond the five
//     catalog commands; no idle roam (spec 10.3 keeps the safe pose while
//     the host is away).
//
// Iteration: 20 ms loop; Y easing is more damped than X (ADR-0005).

#include <Arduino.h>

#include <cstdlib>
#include <string_view>

#include "config/calibration.h"
#include "core/blink_fsm.h"
#include "core/easing.h"
#include "core/mapping.h"
#include "core/protocol.h"
#include "core/watchdog.h"
#include "platform/pins.h"
#include "platform/servo_driver.h"

namespace {

using sirah::eyes::core::BlinkState;

constexpr uint32_t kTickMs = 20;
constexpr float kEaseKx = 0.25F;  // X damping per tick (ADR-0005)
constexpr float kEaseKy = 0.12F;  // Y more damped (ADR-0005)

// Blink cadence 6 s ± 2 s, firmware-owned compile-time constant (A10).
constexpr uint32_t kBlinkCadenceMs = 6000;
constexpr uint32_t kBlinkJitterMs = 2000;

// Watchdog (spec 10): 3 s without any valid activity = link lost.
constexpr uint32_t kWatchdogTimeoutMs = 3000;

constexpr size_t kLineBytes = 64;  // protocol.md 4: 63 payload + NUL

sirah::eyes::core::GazeEaser g_gaze;
sirah::eyes::core::BlinkFSM g_blink;
sirah::eyes::core::Watchdog g_watchdog(kWatchdogTimeoutMs);
sirah::eyes::platform::ServoDriver g_servos;

char g_line[kLineBytes];
size_t g_line_len = 0;
bool g_overflowed = false;

float g_target_x = 0.0F;
float g_target_y = 0.0F;

uint32_t g_auto_interval_ms = kBlinkCadenceMs;
bool g_blink_requested = false;

uint32_t draw_blink_interval() {
  const int32_t j = static_cast<int32_t>(
      (esp_random() % (2 * kBlinkJitterMs + 1)) - kBlinkJitterMs);
  return kBlinkCadenceMs + static_cast<uint32_t>(j);
}

void handle_command(const sirah::eyes::core::ParseResult& r) {
  using sirah::eyes::core::Kind;
  if (r.kind == Kind::Error) {
    Serial.println(sirah::eyes::core::format_err(r.code).c_str());
    return;
  }
  if (r.kind != Kind::Command) return;  // responses from PC ignored
  // Any valid command line is "activity" (spec 10.2): resets the watchdog
  // and, if the link had timed out, arms the once-only READY 1.
  g_watchdog.mark_activity(millis());
  if (g_watchdog.recovery_pending()) {
    g_watchdog.clear_recovery();
    Serial.println(sirah::eyes::core::kReadyLine);
  }
  if (r.name == "TARGET") {
    g_target_x = std::strtof(r.args[0].c_str(), nullptr);
    g_target_y = std::strtof(r.args[1].c_str(), nullptr);
    Serial.println(sirah::eyes::core::kOkLine);
  } else if (r.name == "CENTER") {
    g_target_x = 0.0F;
    g_target_y = 0.0F;
    Serial.println(sirah::eyes::core::kOkLine);
  } else if (r.name == "BLINK") {
    g_blink_requested = true;
    Serial.println(sirah::eyes::core::kOkLine);
  } else if (r.name == "STATUS") {
    const bool blinking = g_blink.state() != BlinkState::Idle;
    Serial.println(
        sirah::eyes::core::format_state(g_gaze.x, g_gaze.y, blinking ? 1 : 0).c_str());
  }
  // HEARTBEAT: accepted silently (keeps the watchdog alive, spec 10.1).
}

void on_line(const char* line, size_t len) {
  handle_command(sirah::eyes::core::parse_line(std::string_view(line, len)));
}

void read_serial() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      if (g_overflowed) {
        g_overflowed = false;
        Serial.println(sirah::eyes::core::format_err(2).c_str());
      } else {
        g_line[g_line_len] = '\0';
        on_line(g_line, g_line_len);
      }
      g_line_len = 0;
    } else if (g_line_len < kLineBytes - 1) {
      g_line[g_line_len++] = c;
    } else {
      g_overflowed = true;  // drain until '\n', then ERR 2 once
    }
  }
}

void write_actuators(uint32_t now_ms) {
  g_servos.set_eye_x(sirah::eyes::core::map_eye_x(g_gaze.x));
  g_servos.set_eye_y(sirah::eyes::core::map_eye_y(g_gaze.y));
  g_servos.set_eyelids(g_blink.progress(now_ms));
}

}  // namespace

void setup() {
  Serial.begin(115200);
  g_servos.init();
  g_auto_interval_ms = draw_blink_interval();
  g_blink.reset();
  Serial.println(sirah::eyes::core::kReadyLine);
}

void loop() {
  read_serial();

  const uint32_t now_ms = millis();

  // Watchdog (spec 10.3): while the link is lost, hold the safe pose CENTER.
  g_watchdog.check(now_ms);
  if (g_watchdog.timed_out()) {
    g_target_x = 0.0F;
    g_target_y = 0.0F;
  }

  const BlinkState prev = g_blink.state();
  if (prev != BlinkState::Idle) {
    // A blink owns the mechanism briefly; defer gaze motion until it opens.
    g_blink.tick(now_ms, g_auto_interval_ms);
  } else {
    if (g_blink_requested) {
      g_blink.trigger(now_ms);
      g_blink_requested = false;
    }
    const bool gaze_settled = g_gaze.tick(g_target_x, g_target_y, kEaseKx, kEaseKy);
    if (gaze_settled) {
      // Auto blinking starts only while the eyes are not turning.
      g_blink.tick(now_ms, g_auto_interval_ms);
    }
  }
  if (prev != BlinkState::Idle && g_blink.state() == BlinkState::Idle) {
    g_auto_interval_ms = draw_blink_interval();
  }

  write_actuators(now_ms);

  delay(kTickMs);
}
