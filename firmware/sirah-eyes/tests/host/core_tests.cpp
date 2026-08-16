// Host tests for firmware core logic (stage 4): mapping, easing, blink
// FSM and protocol serializers. Plain asserts; deterministic inputs only
// (ADR-0010 / P3). Build & run: make.

#include <cassert>
#include <cmath>
#include <cstdio>

#include "core/blink_fsm.h"
#include "core/easing.h"
#include "core/mapping.h"
#include "core/protocol.h"
#include "core/watchdog.h"

namespace {

bool near(float a, float b, float eps = 1e-3F) { return std::fabs(a - b) <= eps; }

void test_mapping_corners() {
  assert(sirah::eyes::core::map_eye_x(-1.0F) == 150.0F);
  assert(sirah::eyes::core::map_eye_x(0.0F) == 110.0F);
  assert(sirah::eyes::core::map_eye_x(1.0F) == 50.0F);
  assert(sirah::eyes::core::map_eye_y(-1.0F) == 40.0F);
  assert(sirah::eyes::core::map_eye_y(0.0F) == 70.0F);
  assert(sirah::eyes::core::map_eye_y(1.0F) == 110.0F);
}

void test_mapping_midpoints() {
  assert(near(sirah::eyes::core::map_eye_x(-0.5F), 130.0F));
  assert(near(sirah::eyes::core::map_eye_x(0.5F), 80.0F));
  assert(near(sirah::eyes::core::map_eye_y(-0.5F), 55.0F));
  assert(near(sirah::eyes::core::map_eye_y(0.5F), 90.0F));
}

void test_mapping_clamps() {
  assert(sirah::eyes::core::map_eye_x(2.0F) == 50.0F);
  assert(sirah::eyes::core::map_eye_x(-2.0F) == 150.0F);
  assert(sirah::eyes::core::map_eye_y(2.0F) == 110.0F);
  assert(sirah::eyes::core::map_eye_y(-2.0F) == 40.0F);
  assert(sirah::eyes::core::clamp_deg_x(110.0F) == 110.0F);
  assert(sirah::eyes::core::clamp_deg_x(200.0F) == 150.0F);
  assert(sirah::eyes::core::clamp_deg_x(-10.0F) == 50.0F);
  assert(sirah::eyes::core::clamp_deg_y(70.0F) == 70.0F);
  assert(sirah::eyes::core::clamp_deg_y(120.0F) == 110.0F);
  assert(sirah::eyes::core::clamp_deg_y(0.0F) == 40.0F);
}

void test_mapping_monotonic() {
  float prev_x = 1e9F;
  float prev_y = -1e9F;
  for (int i = -100; i <= 100; ++i) {
    const float n = static_cast<float>(i) / 100.0F;
    const float x = sirah::eyes::core::map_eye_x(n);
    const float y = sirah::eyes::core::map_eye_y(n);
    // X degrees decrease as normalized goes -1(left) -> +1(right).
    assert(x <= prev_x);
    prev_x = x;
    // Y degrees increase as normalized goes -1(down) -> +1(up).
    assert(y >= prev_y);
    prev_y = y;
  }
}

void test_eyelid_moves() {
  using sirah::eyes::core::EyelidMove;
  const EyelidMove sup_r = sirah::eyes::core::kEyelidSupRight;
  assert(near(sup_r.position(0.0F), 157.0F));
  assert(near(sup_r.position(1.0F), 80.0F));
  assert(near(sup_r.position(0.5F), 118.5F));
  assert(near(sup_r.position(1.5F), 80.0F));  // clamped
  assert(near(sup_r.clamp(50.0F), 80.0F));
  assert(near(sup_r.clamp(200.0F), 157.0F));

  const EyelidMove inf_r = sirah::eyes::core::kEyelidInfRight;
  assert(near(inf_r.position(0.0F), 20.0F));
  assert(near(inf_r.position(1.0F), 69.0F));

  const EyelidMove sup_l = sirah::eyes::core::kEyelidSupLeft;
  assert(near(sup_l.position(0.0F), 87.0F));
  assert(near(sup_l.position(1.0F), 150.0F));

  const EyelidMove inf_l = sirah::eyes::core::kEyelidInfLeft;
  assert(near(inf_l.position(0.5F), 100.0F));
  assert(near(inf_l.clamp(0.0F), 70.0F));
  assert(near(inf_l.clamp(200.0F), 130.0F));
}

void test_easing_single_tick() {
  sirah::eyes::core::GazeEaser g;
  const bool settled = g.tick(1.0F, 1.0F, 0.25F, 0.12F);
  assert(!settled);
  assert(near(g.x, 0.25F));
  assert(near(g.y, 0.12F));
}

void test_easing_converges_no_overshoot() {
  sirah::eyes::core::GazeEaser g;
  float max_x = -1e9F, max_y = -1e9F;
  bool settled = false;
  for (int i = 0; i < 60; ++i) {
    settled = g.tick(1.0F, 1.0F, 0.25F, 0.12F);
    assert(g.x >= 0.0F && g.x <= 1.0F);
    assert(g.y >= 0.0F && g.y <= 1.0F);
    max_x = std::max(max_x, g.x);
    max_y = std::max(max_y, g.y);
  }
  assert(settled);
  assert(max_x <= 1.0F && max_y <= 1.0F);
  assert(near(g.x, 1.0F));
  assert(near(g.y, 1.0F));
  // Without further ticks it must stay settled.
  assert(g.tick(1.0F, 1.0F, 0.25F, 0.12F));
  assert(g.x == 1.0F && g.y == 1.0F);
}

void test_easing_negative_and_axis_independent() {
  sirah::eyes::core::GazeEaser g;
  for (int i = 0; i < 60; ++i) {
    g.tick(-1.0F, -0.5F, 0.25F, 0.12F);
    assert(g.x >= -1.0F && g.x <= 0.0F);
    assert(g.y >= -0.5F && g.y <= 0.0F);
  }
  assert(near(g.x, -1.0F));
  assert(near(g.y, -0.5F));
  // Only X moves toward the new target; Y stays.
  g.tick(0.5F, -0.5F, 0.25F, 0.12F);
  assert(near(g.x, -0.625F));
  assert(near(g.y, -0.5F));
}

void test_blink_initial_idle() {
  sirah::eyes::core::BlinkFSM fsm;
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
  assert(fsm.progress(0) == 0.0F);
}

void test_blink_auto_cycle() {
  sirah::eyes::core::BlinkFSM fsm;
  fsm.tick(0, 6000);                    // arm
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
  fsm.tick(1000, 6000);                 // inside cadence
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
  fsm.tick(6000, 6000);                 // cadence reached -> Closing
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
  assert(fsm.progress(6000) == 0.0F);
  assert(near(fsm.progress(6075), 0.5F));
  assert(fsm.progress(6150) == 1.0F);
  fsm.tick(6150, 6000);                 // closing done -> Closed
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closed);
  assert(fsm.progress(6150) == 1.0F);   // fully closed, sustained
  assert(fsm.progress(6195) == 1.0F);   // sustained mid-phase
  assert(fsm.progress(6240) == 1.0F);   // physical 300 ms close hold
  fsm.tick(6450, 6000);                 // closed done -> Opening
  assert(fsm.state() == sirah::eyes::core::BlinkState::Opening);
  assert(fsm.progress(6450) == 1.0F);   // opening decays 1 -> 0
  assert(near(fsm.progress(6540), 0.5F));
  assert(near(fsm.progress(6620), 1.0F - 170.0F / 180.0F));
  fsm.tick(6630, 6000);                 // opening done -> Idle
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
  assert(fsm.progress(6630) == 0.0F);   // idle: fully open
  // Next auto blink must respect the cadence again.
  fsm.tick(7630, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
  fsm.tick(12630, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
}

void test_blink_trigger_punctual() {
  sirah::eyes::core::BlinkFSM fsm;
  fsm.trigger(1000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
  fsm.tick(1150, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closed);
  fsm.tick(1450, 6000);               // closed hold 300 ms done
  assert(fsm.state() == sirah::eyes::core::BlinkState::Opening);
  fsm.tick(1630, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
}

void test_blink_trigger_mid_blink_discarded() {
  sirah::eyes::core::BlinkFSM fsm;
  fsm.trigger(6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
  fsm.trigger(6050);                    // discarded: no re-entry
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
  fsm.tick(6150, 6000);                 // single close, normal schedule
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closed);
  fsm.trigger(6200);                    // still discarded (Closed)
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closed);
  fsm.tick(6450, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Opening);
  fsm.tick(6630, 6000);
  assert(fsm.state() == sirah::eyes::core::BlinkState::Idle);
}

void test_blink_trigger_only_in_idle_after_cycle() {
  sirah::eyes::core::BlinkFSM fsm;
  fsm.tick(0, 6000);
  fsm.tick(6000, 6000);                 // auto Closing
  fsm.tick(6150, 6000);                 // Closed
  fsm.tick(6450, 6000);                 // Opening
  fsm.tick(6630, 6000);                 // Idle again
  fsm.trigger(7000);                    // must blink now
  assert(fsm.state() == sirah::eyes::core::BlinkState::Closing);
}

void test_protocol_parsing_smoke() {
  using sirah::eyes::core::Kind;
  auto cmd = sirah::eyes::core::parse_line("TARGET 0.5 -1");
  assert(cmd.kind == Kind::Command && cmd.name == "TARGET" && cmd.args.size() == 2);
  auto hb = sirah::eyes::core::parse_line("HEARTBEAT");
  assert(hb.kind == Kind::Command && hb.name == "HEARTBEAT");
  auto err = sirah::eyes::core::parse_line("GARBAGE");
  assert(err.kind == Kind::Error && err.code == 1);
  auto resp = sirah::eyes::core::parse_line("STATE 0.000 0.000 0");
  assert(resp.kind == Kind::Response && resp.name == "STATE");
}

void test_protocol_formatting() {
  using sirah::eyes::core::format_state;
  assert(format_state(0.0F, 0.0F, 0) == "STATE 0.000 0.000 0");
  assert(format_state(-0.0004F, 0.0F, 1) == "STATE 0.000 0.000 1");
  assert(format_state(0.5F, -0.25F, 0) == "STATE 0.500 -0.250 0");
  assert(sirah::eyes::core::format_err(5) == "ERR 5");
}

void test_watchdog_does_not_timeout_with_activity() {
  sirah::eyes::core::Watchdog wd(3000);
  wd.mark_activity(0);
  for (uint32_t t = 1000; t <= 5000; t += 1000) {
    wd.mark_activity(t);
    assert(!wd.check(t));
  }
}

void test_watchdog_times_out_and_holds_while_link_down() {
  sirah::eyes::core::Watchdog wd(3000);
  wd.mark_activity(0);
  assert(!wd.check(1000));
  assert(!wd.check(2999));
  assert(wd.check(3000));   // timeout crossed -> latched
  assert(wd.check(4000));   // stays latched while link stays down
  assert(wd.check(10000));
}

void test_watchdog_any_valid_line_recovers_with_ready_once() {
  sirah::eyes::core::Watchdog wd(3000);
  wd.mark_activity(0);
  assert(wd.check(3000));           // timed out
  assert(!wd.recovery_pending());
  wd.mark_activity(4500);           // first valid line (could be HEARTBEAT/STATUS)
  assert(!wd.check(4500));          // recovered
  assert(wd.recovery_pending());    // READY 1 pending
  wd.clear_recovery();              // firmware emitted READY 1
  assert(!wd.recovery_pending());
  wd.mark_activity(4600);           // further lines do NOT re-arm READY 1
  assert(!wd.recovery_pending());
  assert(!wd.check(5000));
}

void test_watchdog_times_out_again_after_recovery() {
  sirah::eyes::core::Watchdog wd(3000);
  wd.mark_activity(0);
  assert(wd.check(3000));
  wd.mark_activity(4500);
  assert(wd.recovery_pending());
  wd.clear_recovery();
  assert(!wd.check(5000));
  assert(wd.check(7500));           // 3s after the recovery line -> timeout again
  assert(!wd.recovery_pending());
}

}  // namespace

int main() {
  test_mapping_corners();
  test_mapping_midpoints();
  test_mapping_clamps();
  test_mapping_monotonic();
  test_eyelid_moves();
  test_easing_single_tick();
  test_easing_converges_no_overshoot();
  test_easing_negative_and_axis_independent();
  test_blink_initial_idle();
  test_blink_auto_cycle();
  test_blink_trigger_punctual();
  test_blink_trigger_mid_blink_discarded();
  test_blink_trigger_only_in_idle_after_cycle();
  test_protocol_parsing_smoke();
  test_protocol_formatting();
  test_watchdog_does_not_timeout_with_activity();
  test_watchdog_times_out_and_holds_while_link_down();
  test_watchdog_any_valid_line_recovers_with_ready_once();
  test_watchdog_times_out_again_after_recovery();
  std::printf("core_tests: all assertions passed\n");
  return 0;
}
