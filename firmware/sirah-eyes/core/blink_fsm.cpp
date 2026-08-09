#include "core/blink_fsm.h"

namespace sirah::eyes::core {

namespace {
// Hold-off after a completed cycle before any next auto blink may start.
// Guards against timing-edge re-entry and keeps Idle periods monotonic.
constexpr uint32_t kMinCycleGapMs = 1000;
}  // namespace

void BlinkFSM::enter(BlinkState s, uint32_t now_ms) {
  state_ = s;
  entered_ms_ = now_ms;
}

void BlinkFSM::trigger(uint32_t now_ms) {
  if (state_ == BlinkState::Idle) {
    enter(BlinkState::Closing, now_ms);
  }
  // Mid-blink triggers are discarded: no queue, no double-close.
}

void BlinkFSM::reset() {
  state_ = BlinkState::Idle;
  entered_ms_ = 0;
  last_cycle_end_ms_ = 0;
  armed_ = false;
}

void BlinkFSM::tick(uint32_t now_ms, uint32_t auto_interval_ms) {
  switch (state_) {
    case BlinkState::Idle: {
      if (!armed_) {
        // First tick ever: arm the cadence counter.
        armed_ = true;
        last_cycle_end_ms_ = now_ms;
        return;
      }
      if (now_ms - last_cycle_end_ms_ < kMinCycleGapMs) return;
      if (now_ms - last_cycle_end_ms_ >= auto_interval_ms) {
        enter(BlinkState::Closing, now_ms);
      }
      break;
    }
    case BlinkState::Closing:
      if (now_ms - entered_ms_ >= config_.closing_ms) {
        enter(BlinkState::Closed, now_ms);
      }
      break;
    case BlinkState::Closed:
      if (now_ms - entered_ms_ >= config_.closed_ms) {
        enter(BlinkState::Opening, now_ms);
      }
      break;
    case BlinkState::Opening: {
      if (now_ms - entered_ms_ >= config_.opening_ms) {
        state_ = BlinkState::Idle;
        last_cycle_end_ms_ = now_ms;
      }
      break;
    }
  }
}

float BlinkFSM::progress(uint32_t now_ms) const {
  const uint32_t elapsed = now_ms - entered_ms_;
  switch (state_) {
    case BlinkState::Closing: {
      const uint32_t d = config_.closing_ms;
      return elapsed >= d ? 1.0F : static_cast<float>(elapsed) / static_cast<float>(d);
    }
    case BlinkState::Opening: {
      const uint32_t d = config_.opening_ms;
      return elapsed >= d ? 1.0F : static_cast<float>(elapsed) / static_cast<float>(d);
    }
    default:
      return 0.0F;
  }
}

}  // namespace sirah::eyes::core