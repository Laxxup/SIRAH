#include "core/watchdog.h"

namespace sirah::eyes::core {

Watchdog::Watchdog(uint32_t timeout_ms) : timeout_ms_(timeout_ms) {
  last_activity_ms_ = 0;
  timed_out_ = false;
  recovery_pending_ = false;
}

bool Watchdog::check(uint32_t now_ms) {
  if (now_ms - last_activity_ms_ >= timeout_ms_) {
    timed_out_ = true;
  }
  return timed_out_;
}

void Watchdog::mark_activity(uint32_t now_ms) {
  last_activity_ms_ = now_ms;
  if (timed_out_) {
    timed_out_ = false;
    recovery_pending_ = true;  // first valid line after timeout (§10.4)
  }
}

bool Watchdog::recovery_pending() const {
  return recovery_pending_;
}

void Watchdog::clear_recovery() {
  recovery_pending_ = false;
}

}  // namespace sirah::eyes::core