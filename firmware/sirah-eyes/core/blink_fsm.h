// Firmware-owned natural blinking (ADR-0004, A10).
//
// The FSM is completely independent of the PC link: it can blink with no
// host connected. BLINK is ONLY a best-effort punctual trigger — it never
// carries positions and never sequences the eyelids from the outside.
// A trigger arriving mid-blink is discarded (no double-close, no queue,
// no re-entrancy). State machine: Idle -> Closing -> Closed -> Opening ->
// Idle, with entry-time timing and monotonic progress.

#pragma once

#include <cstdint>

namespace sirah::eyes::core {

enum class BlinkState { Idle, Closing, Closed, Opening };

struct BlinkConfig {
  uint32_t closing_ms = 150;
  // Closed-hold 300 ms — physical evidence (verified calibration 2026-08-09):
  // the eyelids need ~300 ms to complete travel before reopening.
  uint32_t closed_ms = 300;
  uint32_t opening_ms = 180;
  // Cadence 6 s ± 2 s (A10): the caller draws the interval in
  // [cadence_ms - jitter_ms, cadence_ms + jitter_ms].
  uint32_t cadence_ms = 6000;
  uint32_t jitter_ms = 2000;
};

class BlinkFSM {
 public:
  // Best-effort trigger: one blink if Idle; discarded otherwise.
  void trigger(uint32_t now_ms);
  void reset();

  // Ticks the FSM. auto_interval_ms is the current drawn cadence (the
  // caller draws the jitter); deterministic and host-testable.
  void tick(uint32_t now_ms, uint32_t auto_interval_ms);

  BlinkState state() const { return state_; }
  // Eyelid progress: Idle 0 (open) -> Closing 0..1 -> Closed 1 (sustained)
  // -> Opening 1..0 -> Idle 0 (open).
  float progress(uint32_t now_ms) const;

  const BlinkConfig& config() const { return config_; }

 private:
  void enter(BlinkState s, uint32_t now_ms);

  BlinkConfig config_;
  BlinkState state_ = BlinkState::Idle;
  uint32_t entered_ms_ = 0;
  uint32_t last_cycle_end_ms_ = 0;
  bool armed_ = false;  // cadence counter armed on first tick
};

}  // namespace sirah::eyes::core