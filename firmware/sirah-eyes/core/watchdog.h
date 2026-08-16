// Host keep-alive watchdog (protocol.md §10, Stage 11).
//
// Mirrors the spec exactly:
//   - Any VALID command line is "activity" and resets the watchdog (§10.2).
//   - After `timeout_ms` without activity the link is considered lost: the
//     caller must ease to the safe pose (CENTER, §10.3) and hold it while
//     the link stays down; blinking continues (ADR-0004).
//   - The first VALID line after a timeout recovers the link and the caller
//     must emit READY 1 exactly once (§10.4); the commanded reference stays
//     at the safe pose until the PC sends a new TARGET/CENTER.

#pragma once

#include <cstdint>

namespace sirah::eyes::core {

class Watchdog {
 public:
  explicit Watchdog(uint32_t timeout_ms);

  // Call every loop tick. Returns true (latched) while the link is lost:
  // `timeout_ms` elapsed without a valid command line (§10.2/§10.3).
  bool check(uint32_t now_ms);

  // Any valid command line (spec 10.2): resets the countdown and, if the
  // link had timed out, arms the once-only READY 1 emission for the caller.
  void mark_activity(uint32_t now_ms);

  // True exactly once per timeout window: after `mark_activity` following a
  // timeout, the caller should emit READY 1 (§10.4).
  bool recovery_pending() const;

  // Clear the recovery flag after READY 1 has been emitted.
  void clear_recovery();

  uint32_t timeout_ms() const { return timeout_ms_; }

 private:
  uint32_t timeout_ms_;
  uint32_t last_activity_ms_;
  bool timed_out_;
  bool recovery_pending_;
};

}  // namespace sirah::eyes::core